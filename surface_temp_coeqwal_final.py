#!/usr/bin/env python
# coding: utf-8

# In[1]:


## 1 ##

# Defines a helper function (find_outflow_col) that automatically detects
# the correct Net Delta Outflow column name in any dataset, even if the column
# name changes (e.g., “NDOI”, “Outflow”, “Net Delta Outflow Index”, “QOUT”,
# “OUT/OUT1”, etc.).
# It standardizes column names, checks for exact or similar matches,
# and returns the correct original column name.

import re
import difflib

def find_outflow_col(df):
    """Returns the ORIGINAL name of the column that contains Net Delta Outflow."""

    def _norm(s: str) -> str:
        s = str(s).strip().upper()
        s = re.sub(r"\s+", "_", s)
        s = re.sub(r"[^A-Z0-9_]", "", s)  # removes characters like ()-/.
        return s

    # Accepted aliases (normalized)
    ALIASES = {
        "NDOI", "NDOI_CFS",
        "QOUT",
        "OUT1", "OUT", "OUT2",
        "OUTFLOW", "OUTFLOW_CFS",
        "NET_DELTA_OUTFLOW", "NET_DELTA_OUTFLOW_INDEX",
        "NETDELTAOUTFLOW", "NETDELTAOUTFLOWINDEX"
    }

    # Mapping: original column name -> normalized name
    norm_map = {c: _norm(c) for c in df.columns}

    # 1) Exact match
    exact = [orig for orig, n in norm_map.items() if n in ALIASES]
    if exact:
        return exact[0]

    # 2) Tolerant regex match
    pat = re.compile(
        r"^(NDOI(_CFS)?|QOUT|OUT1|OUT|OUTFLOW(_CFS)?|NET_?DELTA_?OUTFLOW(_INDEX)?)$"
    )
    for orig, n in norm_map.items():
        if pat.match(n):
            return orig

    # 3) Fuzzy matching
    choices = list(ALIASES)
    for orig, n in norm_map.items():
        if difflib.get_close_matches(n, choices, n=1, cutoff=0.8):
            return orig

    raise KeyError(
        f"Outflow column not found. Available columns: {list(df.columns)}"
    )


# In[2]:


## 2 ##

# Uses the function created in section 1 to download, clean, and merge all
# historical Dayflow data (1929–2024) from the California Data Portal into
# a single CSV file.
# Saved to: outputs/dayflow_1929_2024.csv  (Date, NDOI)

#!/usr/bin/env python
# -*- coding: utf-8 -*-

import io, sys, os, re, requests, pandas as pd

API_DS   = "https://data.cnra.ca.gov/api/3/action/datastore_search"
API_RSRC = "https://data.cnra.ca.gov/api/3/action/resource_show"
UA_HDR   = {"User-Agent": "Mozilla/5.0"}

# ---- Dayflow Results blocks (Portal IDs) ----
BLOCKS = {
    "1929_1939": "ab12e85f-82f4-4723-9973-deeed41b2057",  # CSV
    "1940_1949": "bf58c67c-63b4-47d4-9a25-2b95e5479a0c",  # CSV
    "1950_1955": "9225dbe7-54a6-4466-b360-e66f51407683",  # CSV
    "1956_1969": "3109f3ef-b77b-4288-9ece-3483899d10da",  # CSV
    "1970_1983": "a0a46a1d-bec5-4db9-b331-655e306860ba",  # CSV
    "1984_1996": "cb04e626-9729-4105-af81-f6e5a37f116a",  # CSV
    "1997_2023": "21c377fe-53b8-4bd6-9e1f-2025221be095",  # CSV
    "2024"     : "6a7cb172-fb16-480d-9f4f-0322548fee83",  # XLSX
}

# ---- helper: builds or detects the Date column ----
def build_date_series(df: pd.DataFrame) -> pd.Series:
    cols = {str(c).strip().lower(): c for c in df.columns}

    if "date" in cols:
        s = pd.to_datetime(df[cols["date"]], errors="coerce")
        if s.notna().any():
            return s

    # fallback: Year / Month / Day (if present)
    has = {k: v for k, v in cols.items() if k in ("year", "month", "day")}
    if {"year", "month", "day"}.issubset(has):
        return pd.to_datetime(
            dict(
                year=df[has["year"]],
                month=df[has["month"]],
                day=df[has["day"]],
            ),
            errors="coerce",
        )

    raise KeyError(
        f"Could not find a 'Date' column or (Year, Month, Day). Headers: {list(df.columns)}"
    )

frames = []
os.makedirs("outputs", exist_ok=True)

for tag, rid in BLOCKS.items():
    print(f"⇢ Processing dataset {tag} …")

    # A) First try via DataStore (CSV)
    df_raw = None
    try:
        js = requests.get(
            API_DS,
            params={"resource_id": rid, "limit": 50000},
            headers=UA_HDR,
            timeout=60,
        ).json()
        if js.get("success") and "records" in js.get("result", {}):
            df_raw = pd.DataFrame(js["result"]["records"])
    except Exception:
        pass

    # B) If not available via DataStore, try direct download (XLSX / CSV)
    if df_raw is None or df_raw.empty:
        try:
            meta = requests.get(
                API_RSRC,
                params={"id": rid},
                headers=UA_HDR,
                timeout=30,
            ).json()
            url = meta["result"]["url"]
            raw = requests.get(url, headers=UA_HDR, timeout=120).content
            try:
                df_raw = pd.read_excel(io.BytesIO(raw), engine="openpyxl")
            except Exception:
                df_raw = pd.read_csv(io.BytesIO(raw))
        except Exception as e:
            print(f"   ✖  Could not retrieve {tag}: {e}")
            continue

    # --- detect Date and Outflow (reuses function from section 1) ---
    try:
        date_series = build_date_series(df_raw)
        outcol = find_outflow_col(df_raw)   # <<<<<<<<<< reuses section 1
    except Exception as e:
        print(f"   ⚠  Unexpected headers in {tag}. Skipping. → {e}")
        print("      Headers:", list(df_raw.columns))
        continue

    df = (
        pd.DataFrame(
            {
                "Date": date_series,
                "NDOI": pd.to_numeric(df_raw[outcol], errors="coerce"),
            }
        )
        .dropna(subset=["Date"])
        .sort_values("Date")
    )

    frames.append(df)

# ---- concatenate and export ----
if not frames:
    sys.exit("❌ No blocks could be processed.")

all_df = (
    pd.concat(frames, ignore_index=True)
    .drop_duplicates("Date")
    .sort_values("Date")
)

out_path = os.path.join("outputs", "dayflow_1929_2024.csv")
all_df.to_csv(out_path, index=False)

print(f"\n✔  CSV generated: {out_path}  –  rows: {len(all_df):,}")


# In[3]:


## 3 ##

# Downloads the official Water Year Type records (1906–present)
# for the Sacramento and San Joaquin Valleys from California’s Data Portal.
# Reshapes the data into wide format (WY, Sac_Type, SJV_Type)
# and saves it as outputs/water_year_type.csv

#!/usr/bin/env python
# -*- coding: utf-8 -*-

import requests, pandas as pd, os

RID = "105614f4-c71d-4191-b1f9-ea510afd8b62"
API = "https://data.ca.gov/api/3/action/datastore_search"

def get_all_records(rid):
    records, start, rows = [], 0, 50000
    while True:
        js = requests.get(
            API,
            params={"resource_id": rid, "limit": rows, "offset": start},
            timeout=60
        ).json()
        if not js.get("success"):
            raise RuntimeError(js.get("error"))
        recs = js["result"]["records"]
        records.extend(recs)
        if len(recs) < rows:
            break
        start += rows
    return pd.DataFrame(records)

# 1) download long table
long = get_all_records(RID)

# normalize headers
long.columns = [c.strip() for c in long.columns]

# 2) pivot → wide format
wide = (long.pivot(index="WY", columns="Area", values="WYT")
            .reset_index()
            .rename(columns={
                "Sacramento Valley":  "Sac_Type",
                "San Joaquin Valley": "SJV_Type"}))

wide["WY"] = wide["WY"].astype(int)  # 2000.0 → 2000

# 3) save
os.makedirs("outputs", exist_ok=True)
wide.to_csv("outputs/water_year_type.csv", index=False)
print("✓ outputs/water_year_type.csv — rows:", len(wide))


# In[4]:


## 3.1 ##

# Build a single daily CSV joined with official Water Year (Oct→Sep)
# Inputs:
#   - outputs/dayflow_1929_2024.csv    (Date, NDOI)
#   - outputs/water_year_type.csv      (WY, Sac_Type, SJV_Type)
# Output: outputs/dayflow_wyt_daily.csv    (WY, NDOI, Sac_Type, SJV_Type, Date)

#!/usr/bin/env python
# -*- coding: utf-8 -*-

import os
import pandas as pd

DAYFLOW_CSV = os.path.join("outputs", "dayflow_1929_2024.csv")
WYT_CSV     = os.path.join("outputs", "water_year_type.csv")
OUT_CSV     = os.path.join("outputs", "dayflow_wyt_daily.csv")

if not os.path.exists(DAYFLOW_CSV):
    raise SystemExit(f"Missing {DAYFLOW_CSV} — run chunk 2 first.")
if not os.path.exists(WYT_CSV):
    raise SystemExit(f"Missing {WYT_CSV} — run chunk 3 first.")

df_day = pd.read_csv(DAYFLOW_CSV, parse_dates=["Date"])
df_wyt = pd.read_csv(WYT_CSV)

df_day = df_day.dropna(subset=["Date"]).copy()
df_day["Date"] = pd.to_datetime(df_day["Date"]).dt.normalize()
df_day["NDOI"] = pd.to_numeric(df_day["NDOI"], errors="coerce")

# Official Water Year: add +3 months so Oct–Dec map to next year; then take calendar year
df_day["WY"] = (df_day["Date"] + pd.DateOffset(months=3)).dt.year.astype(int)

def normalize_wyt_col(s: pd.Series) -> pd.Series:
    m = {
        "WET": "W",
        "ABOVE NORMAL": "AN",
        "BELOW NORMAL": "BN",
        "DRY": "D",
        "CRITICAL": "C",
    }
    out = s.astype(str).str.strip()
    upper = out.str.upper()
    return upper.map(m).fillna(upper)

df_wyt["WY"] = pd.to_numeric(df_wyt["WY"], errors="coerce").astype("Int64")
df_wyt = df_wyt.dropna(subset=["WY"]).copy()
df_wyt["WY"] = df_wyt["WY"].astype(int)
df_wyt["Sac_Type"] = normalize_wyt_col(df_wyt["Sac_Type"])
df_wyt["SJV_Type"] = normalize_wyt_col(df_wyt["SJV_Type"])

joined = df_day.merge(df_wyt, on="WY", how="left")

joined = joined[["WY", "NDOI", "Sac_Type", "SJV_Type", "Date"]].copy()
joined["Date"] = joined["Date"].dt.strftime("%Y-%m-%d")

os.makedirs("outputs", exist_ok=True)
joined.to_csv(OUT_CSV, index=False)
print(f"✔ Wrote {OUT_CSV} — rows: {len(joined):,}")


# In[ ]:


##### 4 ##

# Interactive NDOI + Water Year Type Query (from unified CSV created in 3.1)
# Uses the pre-joined file "dayflow_wyt_daily.csv" (created in chunk 3.1),
# which already contains daily Net Delta Outflow (NDOI), Sacramento and
# San Joaquin Water-Year-Type codes, and the official Water Year (WY).
# Prompts the user for NDOI range and optional WYT codes, shows all
# matching rows with the same columns and order as the source CSV
# (WY, NDOI, Sac_Type, SJV_Type, Date), saves all matches to
# outputs/match_results.csv, and lets the user pick a subset of dates
# to save for downstream Landsat steps at inputs/target_dates.csv.

#!/usr/bin/env python
# -*- coding: utf-8 -*-

import os, sys, textwrap
import pandas as pd

JOINED_CSV = os.path.join("outputs", "dayflow_wyt_daily.csv")

if not os.path.exists(JOINED_CSV):
    sys.exit("outputs/dayflow_wyt_daily.csv not found — run chunk 3.1 first!")

df = pd.read_csv(JOINED_CSV, parse_dates=["Date"])
df = df[["WY", "NDOI", "Sac_Type", "SJV_Type", "Date"]].copy()

min_wy, max_wy = int(df["WY"].min()), int(df["WY"].max())
min_yr = df["Date"].min().year
max_yr = df["Date"].max().year

EXPL = textwrap.dedent(f"""
    WATER-YEAR TYPE (WYT)
      Hydrologic class assigned by DWR for each water-year (Oct → Sep):
        W  = Wet
        AN = Above Normal
        BN = Below Normal
        D  = Dry
        C  = Critical
      Data available: from {min_wy} to {max_wy}

    NDOI (Net Delta Outflow Index)
      Daily net freshwater outflow from the legal Delta toward Suisun Bay.
      Units: cubic-feet-per-second (cfs).
      Daily data available: from October/01/{min_yr} to September/30/{max_yr}
""")
print(EXPL)

VALID_WYT = {"W", "AN", "BN", "D", "C"}

# Reference-only SQL (kept to preserve the original query structure, not executed)
sql_reference = """
    SELECT Date, NDOI,
           Sac_Type AS Sac_WYT,
           SJV_Type AS SJV_WYT
    FROM   v_dayflow_wyt
    WHERE  NDOI BETWEEN ? AND ?
      AND  (? IS NULL OR UPPER(TRIM(Sac_Type)) = UPPER(?))
      AND  (? IS NULL OR UPPER(TRIM(SJV_Type)) = UPPER(?))
    ORDER BY Date;
"""

while True:
    try:
        sac = input("Enter Sacramento WYT [W/AN/BN/D/C] (blank = any): ").strip().upper() or None
        sjv = input("Enter San Joaquin WYT [W/AN/BN/D/C] (blank = any): ").strip().upper() or None

        min_txt = input("Enter minimum NDOI (cfs) [blank = no limit]: ").strip()
        max_txt = input("Enter maximum NDOI (cfs) [blank = no limit]: ").strip()
        min_ndoi = float(min_txt) if min_txt else -1e12
        max_ndoi = float(max_txt) if max_txt else  1e12
        if min_ndoi > max_ndoi:
            min_ndoi, max_ndoi = max_ndoi, min_ndoi

        df_f = df[
            (df["NDOI"].between(min_ndoi, max_ndoi, inclusive="both")) &
            (True if sac is None else df["Sac_Type"].astype(str).str.strip().str.upper() == sac) &
            (True if sjv is None else df["SJV_Type"].astype(str).str.strip().str.upper() == sjv)
        ].copy()

        df_f = df_f.sort_values("Date")

        print(f"\nMatches: {len(df_f):,} days")

        if not df_f.empty:
            os.makedirs("outputs", exist_ok=True)
            df_f[["WY", "NDOI", "Sac_Type", "SJV_Type", "Date"]].to_csv("outputs/match_results.csv", index=False)
            print("✓ Saved ALL matches to outputs/match_results.csv")

            print("\nAll matching rows:\n")
            print(df_f[["WY", "NDOI", "Sac_Type", "SJV_Type", "Date"]].to_string(index=False))

            choice = input(
                "\nPick dates for satellite search "
                "(all / none / comma-separated list / start:end): "
            ).strip().lower()

            chosen = df_f.copy()
            if choice == "none":
                chosen = chosen.iloc[0:0]
            elif choice == "all" or choice == "":
                pass
            elif ":" in choice:
                try:
                    a_str, b_str = choice.split(":", 1)
                    a = pd.to_datetime(a_str).date()
                    b = pd.to_datetime(b_str).date()
                    if a > b: a, b = b, a
                    mask = (chosen["Date"].dt.date >= a) & (chosen["Date"].dt.date <= b)
                    chosen = chosen.loc[mask]
                except Exception as e:
                    print("⚠ Could not parse range; keeping all matches.", e)
            else:
                want, misses = [], []
                all_days = set(df_f["Date"].dt.date)
                for tok in choice.split(","):
                    tok = tok.strip()
                    if not tok:
                        continue
                    try:
                        d = pd.to_datetime(tok).date()
                        (want if d in all_days else misses).append(tok)
                    except Exception:
                        misses.append(tok)
                chosen = chosen[chosen["Date"].dt.date.isin(pd.to_datetime(want).date)] if want else chosen.iloc[0:0]
                if misses:
                    print("Note: ignored (not in matches):", ", ".join(misses))

            os.makedirs("inputs", exist_ok=True)
            chosen.sort_values("Date").to_csv("inputs/target_dates.csv", index=False)
            print(f"✓ Saved selected dates to inputs/target_dates.csv — {len(chosen)} rows")
            if len(chosen):
                print("\nSelected dates (first 20):")
                print(chosen.head(20)[["WY", "NDOI", "Sac_Type", "SJV_Type", "Date"]].to_string(index=False))
            else:
                print("\nNo dates selected.")
        else:
            print("No dates satisfy those conditions.")

    except Exception as e:
        print("⚠", e)

    again = input("\nRefine the search? (y/n): ").strip().lower()
    if again != "y":
        break


# In[ ]:


## 5 ##

# Lists and matches Landsat Collection 2 Level-2 scenes directly from
# the usgs-landsat S3 bucket (Requester Pays) without using STAC.
# For each target date (± 7 days) and specified Path/Rows, it finds the
# nearest available scenes, checks for key assets (ST_B10, ST_B6, LWIR11,
# QA_PIXEL), and saves a catalog of results to outputs/scene_catalog_s3only.csv.
#
# Notes:
#   - Cloud cover is NOT included here (left as None).
#   - LWIR11 is recorded IF it exists for the scene.
#   - QA_PIXEL is recorded IF it exists for the scene.

import os, re
import pandas as pd
from datetime import datetime
import boto3
from botocore.exceptions import ClientError

TARGETS_CSV     = "inputs/target_dates.csv"
WINDOW_DAYS     = 7
WRS_PATH        = 44
WRS_ROWS        = {33, 34}
BUCKET          = "usgs-landsat"
REGION          = os.environ.get("AWS_REGION", "us-west-2")
REQUEST_PAYER   = "requester"
OUT_CSV         = "outputs/scene_catalog_s3only.csv"

os.makedirs("outputs", exist_ok=True)

SUBDIRS = ["oli-tirs", "etm", "tm"]  # L8/L9, L7, L5/4

def year_span_for_date(date_obj, window_days):
    start = (pd.Timestamp(date_obj) - pd.Timedelta(days=window_days)).date()
    end   = (pd.Timestamp(date_obj) + pd.Timedelta(days=window_days)).date()
    return range(start.year, end.year + 1)

def list_product_dirs(s3, subdir, year, path, row):
    """
    Returns a list of product prefixes (folders), e.g.:
    'collection02/level-2/standard/oli-tirs/2023/044/033/LC09_L2SP_044033_20231216_20231217_02_T1/'
    """
    prefix = f"collection02/level-2/standard/{subdir}/{year:04d}/{path:03d}/{row:03d}/"
    paginator = s3.get_paginator("list_objects_v2")
    kwargs = dict(Bucket=BUCKET, Prefix=prefix, Delimiter="/", RequestPayer=REQUEST_PAYER)
    prefixes = []
    for page in paginator.paginate(**kwargs):
        for cp in page.get("CommonPrefixes", []):
            p = cp.get("Prefix")
            if p and p.startswith(prefix):
                prefixes.append(p)
    return prefixes

def product_id_from_prefix(pref):
    if not pref.endswith("/"):
        return None
    pid = pref.rstrip("/").split("/")[-1]
    return pid if pid else None

def date_from_pid(pid):
    m = re.search(r"_[0-9]{6}_(\d{8})_", pid)
    if not m:
        return None
    try:
        return datetime.strptime(m.group(1), "%Y%m%d").date()
    except Exception:
        return None

def subdir_from_pid(pid):
    u = pid.upper()
    if u.startswith(("LC08", "LC09")): return "oli-tirs"
    if u.startswith("LE07"):           return "etm"
    if u.startswith(("LT05","LT04")):  return "tm"
    return "oli-tirs"

def build_key(pid, suffix):
    m_pr = re.search(r"_(\d{6})_", pid)
    m_dt = re.search(r"_(\d{8})_", pid)
    if not (m_pr and m_dt):
        return None
    pr = m_pr.group(1); path, row = pr[:3], pr[3:]
    year = m_dt.group(1)[:4]
    sub = subdir_from_pid(pid)
    return f"collection02/level-2/standard/{sub}/{year}/{path}/{row}/{pid}/{pid}_{suffix}.TIF"

def s3_head_exists(s3, key):
    try:
        s3.head_object(Bucket=BUCKET, Key=key, RequestPayer=REQUEST_PAYER)
        return True
    except ClientError:
        return False

s3 = boto3.client("s3", region_name=REGION)

targets = (pd.read_csv(TARGETS_CSV, parse_dates=["Date"])
             .dropna(subset=["Date"])
             .drop_duplicates("Date")
             .sort_values("Date"))
assert len(targets), f"{TARGETS_CSV} has no dates."

print(
    f"Target dates: {len(targets)}  |  range: {targets['Date'].dt.date.min()} → {targets['Date'].dt.date.max()}  |  window ±{WINDOW_DAYS} days"
)

records = []

# Cache S3 listings (speed-up only; does not change results)
_list_cache = {}

for t in targets["Date"].dt.date.tolist():
    candidates = []
    for row in sorted(WRS_ROWS):
        for y in year_span_for_date(t, WINDOW_DAYS):
            for sub in SUBDIRS:
                cache_key = (sub, y, WRS_PATH, row)
                if cache_key in _list_cache:
                    prefs = _list_cache[cache_key]
                else:
                    prefs = list_product_dirs(s3, sub, y, WRS_PATH, row)
                    _list_cache[cache_key] = prefs

                for pref in prefs:
                    pid = product_id_from_prefix(pref)
                    if not pid:
                        continue
                    acq = date_from_pid(pid)
                    if not acq:
                        continue
                    delta = abs((acq - t).days)
                    if delta <= WINDOW_DAYS:
                        candidates.append((pid, acq, row, delta))

    if not candidates:
        print(f"  {t}: no scenes within ±{WINDOW_DAYS} days (S3 listing only).")
        for row in sorted(WRS_ROWS):
            records.append({
                "TargetDate": str(t), "MatchedDate": None, "DeltaDays": None, "MatchType": "none",
                "SceneID": None, "Platform": None, "CloudCover": None,
                "Path": WRS_PATH, "Row": row,
                "Has_ST_B10": False, "st_b10_http": None, "st_b10_s3": None,
                "Has_ST_B6": False,  "st_b6_http":  None, "st_b6_s3":  None,
                "Has_LWIR":  False,  "lwir_http":   None, "lwir_s3":   None,
                "Has_QA_PIXEL": False, "QA_PIXEL_http": None, "QA_PIXEL_s3": None,
            })
        continue

    dfc = (pd.DataFrame(candidates, columns=["PID","AcqDate","Row","DeltaDays"])
             .sort_values(["Row","DeltaDays","AcqDate"]))

    for row, grp in dfc.groupby("Row"):
        pid, acq, dd = grp.iloc[0][["PID","AcqDate","DeltaDays"]]
        match_type = "exact" if acq == t else "nearest"

        k_st10 = build_key(pid, "ST_B10")
        k_st6  = build_key(pid, "ST_B6")
        k_lwir = build_key(pid, "LWIR11")
        k_qa   = build_key(pid, "QA_PIXEL")

        has_st6  = s3_head_exists(s3, k_st6)  if k_st6  else False
        has_st10 = s3_head_exists(s3, k_st10) if k_st10 else False
        has_lwir = s3_head_exists(s3, k_lwir) if k_lwir else False
        has_qa   = s3_head_exists(s3, k_qa)   if k_qa   else False

        def http_from_key(key):
            return f"https://{BUCKET}.s3.us-west-2.amazonaws.com/{key}" if key else None

        rec = {
            "TargetDate": str(t),
            "MatchedDate": str(acq),
            "DeltaDays": int(dd),
            "MatchType": match_type,
            "SceneID": pid,
            "Platform": ("landsat-9" if pid.startswith("LC09") else
                         "landsat-8" if pid.startswith("LC08") else
                         "landsat-7" if pid.startswith("LE07") else
                         "landsat-5" if pid.startswith("LT05") else
                         "landsat-4" if pid.startswith("LT04") else None),
            "CloudCover": None,  # Not extracted in this S3-only listing step
            "Path": f"{WRS_PATH:03d}",
            "Row":  f"{row:03d}",
            "Has_ST_B10": has_st10,
            "st_b10_http": http_from_key(k_st10) if has_st10 else None,
            "st_b10_s3":   f"s3://{BUCKET}/{k_st10}" if has_st10 else None,
            "Has_ST_B6": has_st6,
            "st_b6_http": http_from_key(k_st6) if has_st6 else None,
            "st_b6_s3":   f"s3://{BUCKET}/{k_st6}" if has_st6 else None,
            "Has_LWIR": has_lwir,
            "lwir_http": http_from_key(k_lwir) if has_lwir else None,
            "lwir_s3":   f"s3://{BUCKET}/{k_lwir}" if has_lwir else None,
            "Has_QA_PIXEL": has_qa,
            "QA_PIXEL_http": http_from_key(k_qa) if has_qa else None,
            "QA_PIXEL_s3":   f"s3://{BUCKET}/{k_qa}" if has_qa else None,
        }
        records.append(rec)

df = (pd.DataFrame.from_records(records)
        .sort_values(["TargetDate","Row","DeltaDays"], na_position="last"))
df.to_csv(OUT_CSV, index=False, encoding="utf-8")
print(f"\n✓ Saved {OUT_CSV}  |  rows: {len(df)}")
if len(df):
    print(df.head(10).to_string(index=False))


# In[ ]:


from utils_s3_rasterio import (
    configure_aws_gdal_env,
    make_s3_client,
    s3_head_exists,
    gdal_open_from_s3,
    load_aoi_geojson,
    pick_first_s3,
    close_quietly,
)


# In[ ]:


## 6 ##

# Builds per-date temperature mosaics from Landsat assets listed in
# outputs/scene_catalog_s3only.csv, reading directly from S3 (Requester Pays).
# For each matched date, it selects ST_B10/ST_B6/LWIR, warps/resamples,
# mosaics, clips to the AOI (inputs/delta_legal_4326.geojson), converts
# surface temperature to Celsius, writes GeoTIFFs, and packages them into
# a single ZIP at outputs/mosaicos/mosaicos_celsius_full_nomasks.zip.
# AWS region/credentials are configured and optimized for GDAL/Rasterio S3 access.

# Mosaics with no masks yet


## 6 ##
# Builds per-date temperature mosaics from Landsat assets listed in
# outputs/scene_catalog_s3only.csv, reading directly from S3 (Requester Pays).
# For each matched date, it selects ST_B10/ST_B6/LWIR, warps/resamples,
# mosaics, clips to the AOI (inputs/delta_legal_4326.geojson), converts
# surface temperature to Celsius, writes GeoTIFFs, and packages them into
# a single ZIP at outputs/mosaicos/mosaicos_celsius_full_nomasks.zip.

# -*- coding: utf-8 -*-
import os, tempfile, shutil, zipfile
import numpy as np
import pandas as pd
import rasterio as rio
from rasterio.mask import mask
from rasterio.warp import transform_geom
from rasterio.merge import merge
from rasterio.vrt import WarpedVRT
from rasterio.enums import Resampling
from rasterio.features import bounds as feat_bounds

from utils_s3_rasterio import (
    configure_aws_gdal_env,
    make_s3_client,
    s3_head_exists,
    gdal_open_from_s3,
    load_aoi_geojson,
    pick_first_s3,
    close_quietly,
)

# ----------------- CONFIG -----------------
CAT_CSV      = "outputs/scene_catalog_s3only.csv"   # your S3-only CSV
AOI_GEOJSON  = "inputs/delta_legal_4326.geojson"    # EPSG:4326
ZIP_SALIDA   = "outputs/mosaicos/mosaicos_celsius_full_nomasks.zip"

# AWS/GDAL
configure_aws_gdal_env(region="us-west-2", requester_payer="requester")
S3 = make_s3_client()

# ----------------- LOAD CATALOG -----------------
df = pd.read_csv(CAT_CSV)
for col in ["Path", "Row"]:
    if col in df.columns:
        df[col] = pd.to_numeric(df[col], errors="coerce")
df = df.sort_values(["MatchedDate", "Row"])
assert "MatchedDate" in df.columns and "SceneID" in df.columns, "Key columns are missing from the CSV."
expected_cols = {"st_b10_s3", "st_b6_s3", "lwir_s3"}
missing = [c for c in expected_cols if c not in df.columns]
if missing:
    print("⚠️ Your CSV is missing expected columns:", missing)

# ----------------- AOI -----------------
aoi_wgs84 = load_aoi_geojson(AOI_GEOJSON)

# ----------------- CONSTANTS -----------------
# Landsat C2 Surface Temperature: K = DN * 0.00341802 + 149.0
# Celsius: C = K - 273.15
SCALE_ST = 0.00341802
OFFSET_ST = 149.0

def pick_asset_s3_from_row(r):
    """Selects the best asset using ONLY what is in the CSV."""
    _, s3_url = pick_first_s3(r, ["st_b10_s3", "st_b6_s3", "lwir_s3"])
    return (None, s3_url) if s3_url else (None, None)

def mosaico_fecha_a_K_en_path(mdate, recs, aoi_wgs84, out_tif, dst_res=None, resampling="bilinear"):
    """
    Per-date mosaic -> AOI clip -> converts to Celsius -> writes GeoTIFF to out_tif.
    Returns dict with info, or None if failed.
    """
    # 1) Base for CRS/resolution
    primera_s3 = None
    for r in recs:
        _, s3_url = pick_asset_s3_from_row(r)
        if s3_url and s3_head_exists(S3, s3_url):
            primera_s3 = s3_url
            break
    if not primera_s3:
        print(f"  × {mdate}: no valid scenes.")
        return None

    with gdal_open_from_s3(S3, primera_s3) as src0:
        dst_crs = src0.crs
        if dst_res is None:
            xres = abs(src0.transform.a)
            yres = abs(src0.transform.e)
            dst_res = (xres, yres)
        aoi_dst = transform_geom("EPSG:4326", dst_crs.to_string(), aoi_wgs84, precision=6)
        aoi_bounds = feat_bounds(aoi_dst)

    rs = {"bilinear": Resampling.bilinear, "nearest": Resampling.nearest}.get(resampling, Resampling.bilinear)
    vrt_list, src_list = [], []
    try:
        usadas = 0
        for r in recs:
            _, s3_url = pick_asset_s3_from_row(r)
            if not s3_url or not s3_head_exists(S3, s3_url):
                print(f"  × {r.get('SceneID')}: no valid asset → {s3_url}")
                continue
            try:
                src = gdal_open_from_s3(S3, s3_url)
            except Exception as e:
                print(f"  × {r.get('SceneID')}: failed to open → {s3_url} | {e}")
                continue

            vrt = WarpedVRT(
                src,
                dst_crs=dst_crs,
                resampling=rs,
                transform=None,
                resolution=dst_res,
                nodata=np.nan,
                add_alpha=False,
            )
            src_list.append(src)
            vrt_list.append(vrt)
            usadas += 1

        if not vrt_list:
            print(f"  × {mdate}: could not open any scene in VRT.")
            return None

        # 3) Merge limited to AOI bbox (mosaic of ALL scenes for the date)
        mosaic_dn, mosaic_transform = merge(vrt_list, bounds=aoi_bounds, nodata=np.nan, dtype="float32")

        # 4) Exact clip to AOI polygon
        profile = vrt_list[0].profile.copy()
        profile.update({
            "driver": "GTiff", "height": mosaic_dn.shape[1], "width": mosaic_dn.shape[2],
            "count": 1, "dtype": "float32", "crs": dst_crs, "transform": mosaic_transform, "nodata": np.nan,
            "compress": "DEFLATE", "predictor": 3, "zlevel": 6, "tiled": True,
            "blockxsize": 512, "blockysize": 512
        })

        tmp_path = out_tif + ".__tmp__.tif"
        with rio.open(tmp_path, "w", **profile) as dst:
            dst.write(mosaic_dn[0], 1)

        with rio.open(tmp_path) as tmp_src:
            clipped_dn, clipped_transform = mask(tmp_src, [aoi_dst], crop=True, nodata=np.nan)
            clipped_profile = tmp_src.profile.copy()
            clipped_profile.update({"height": clipped_dn.shape[1], "width": clipped_dn.shape[2], "transform": clipped_transform})

        # 5) Celsius and save
        K = clipped_dn.astype("float32") * SCALE_ST + OFFSET_ST
        C = K - 273.15

        with rio.open(out_tif, "w", **clipped_profile) as dst:
            dst.write(C[0], 1)
            dst.update_tags(**{
                "UNITS": "CELSIUS",
                "SCALE_APPLIED": str(SCALE_ST),
                "OFFSET_APPLIED": str(OFFSET_ST),
                "CONVERSION": "Kelvin_to_Celsius",
                "AOI": "DELTA",
                "NOTE": "NO_MASKS_APPLIED"
            })

        os.remove(tmp_path)
        print(f"  ✓ {mdate}: wrote {os.path.basename(out_tif)} | scenes_used={usadas} | shape={C.shape}")
        return {"dst_crs": dst_crs, "n_scenes": usadas}

    finally:
        close_quietly(vrt_list)
        close_quietly(src_list)

# ----------------- MAIN FLOW: create a SINGLE ZIP -----------------
os.makedirs(os.path.dirname(ZIP_SALIDA), exist_ok=True)

tmp_dir = tempfile.mkdtemp(prefix="mosaicos_c_")
print(f"Temporary Directory: {tmp_dir}")

rutas_tifs = []

try:
    for mdate, grp in df.groupby("MatchedDate"):
        recs = grp.to_dict(orient="records")
        if not recs:
            continue

        grp_sorted = grp.sort_values(["Row", "SceneID"])
        scene_id_repr = str(grp_sorted.iloc[0]["SceneID"]).strip()

        out_tif = os.path.join(tmp_dir, f"{scene_id_repr}.tif")
        print(f"\n=== MatchedDate: {mdate} | scenes in CSV: {len(recs)} | name: {scene_id_repr}.tif ===")

        info = mosaico_fecha_a_K_en_path(mdate, recs, aoi_wgs84, out_tif, dst_res=None, resampling="bilinear")
        if info is None:
            continue
        rutas_tifs.append(out_tif)

    if rutas_tifs:
        if os.path.exists(ZIP_SALIDA):
            os.remove(ZIP_SALIDA)
        with zipfile.ZipFile(ZIP_SALIDA, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            for tif_path in rutas_tifs:
                zf.write(tif_path, arcname=os.path.basename(tif_path))
        print(f"\n✓ ZIP created: {ZIP_SALIDA} (layers: {len(rutas_tifs)})")
    else:
        print("\n× No mosaics were generated; there is no ZIP.")
finally:
    try:
        shutil.rmtree(tmp_dir)
        print(f"Temporaries deleted: {tmp_dir}")
    except Exception as e:
        print(f"⚠️ Could not delete temporaries {tmp_dir}: {e}")

print("\nDone. Download and open the ZIP file; inside you'll find the GeoTIFFs in Celsius, clipped to the Delta (one per date).")


# In[ ]:


## 7 ##
# Connects to AWS S3 to open the TIFFs directly from S3
# Mosaics and creates a single thermal raster in digital numbers (DN)
# Builds and aligns the quality mask (QA_PIXEL)

# -*- coding: utf-8 -*-

## 7 ##
# Connects to AWS S3 to open the TIFFs directly from S3
# Mosaics and creates a single thermal raster in digital numbers (DN)
# Builds and aligns the quality mask (QA_PIXEL)

# -*- coding: utf-8 -*-

import os, tempfile, shutil, zipfile
import numpy as np
import pandas as pd
import rasterio as rio
from rasterio.mask import mask
from rasterio.warp import transform_geom
from rasterio.merge import merge
from rasterio.vrt import WarpedVRT
from rasterio.enums import Resampling
from rasterio.features import bounds as feat_bounds
from shapely.geometry import shape, mapping

from utils_s3_rasterio import (
    configure_aws_gdal_env,
    make_s3_client,
    s3_head_exists,
    gdal_open_from_s3,
    load_aoi_geojson,
    pick_first_s3,
    close_quietly,
)

# === Config ===
CAT_CSV     = "outputs/scene_catalog_s3only.csv"
AOI_GEOJSON = "inputs/delta_legal_4326.geojson"
ZIP_SALIDA  = "outputs/mosaicos/mosaicos_celsius_wateronly.zip"

# Landsat C2 L2: Kelvin = DN*0.00341802 + 149.0 ; Celsius = Kelvin - 273.15
SCALE_ST = 0.00341802
OFFSET_ST = 149.0
K_TO_C    = -273.15

# AWS / GDAL
configure_aws_gdal_env(region="us-west-2", requester_payer="requester")
S3 = make_s3_client()

def pick_st_from_row(r):
    _, v = pick_first_s3(r, ["st_b10_s3", "st_b6_s3", "lwir_s3"])
    return v

def pick_qa_from_row(r):
    _, v = pick_first_s3(r, ["QA_PIXEL_s3", "qa_pixel_s3"])
    return v

# QA_PIXEL bits (L2 C2): 1 Dilated, 2 Cirrus, 3 Cloud, 4 Cloud shadow, 5 Snow, 7 Water
BIT_DILATED = 1; BIT_CIRRUS = 2; BIT_CLOUD = 3; BIT_CSHADOW = 4; BIT_SNOW = 5; BIT_WATER = 7
def bit_is_set(u16, bitpos): return ((u16 >> bitpos) & 1).astype(bool)

# === Load ===
df = pd.read_csv(CAT_CSV)
for c in ["Path","Row"]:
    if c in df.columns: df[c] = pd.to_numeric(df[c], errors="coerce")
assert "MatchedDate" in df.columns and "SceneID" in df.columns, "CSV must have MatchedDate and SceneID"
aoi = load_aoi_geojson(AOI_GEOJSON)

# === Per-date loop (correct mosaic) ===
os.makedirs(os.path.dirname(ZIP_SALIDA), exist_ok=True)
tmp_dir = tempfile.mkdtemp(prefix="wateronly_c_")
print("Temp dir:", tmp_dir)
salidas = []

try:
    for mdate, grp in df.groupby("MatchedDate"):
        recs = grp.to_dict(orient="records")
        if not recs: continue

        # Choose base scene for the grid
        base_st = None
        for r in recs:
            u = pick_st_from_row(r)
            if u and s3_head_exists(S3, u):
                base_st = u
                break
        if not base_st:
            print("×", mdate, "no valid ST")
            continue

        with gdal_open_from_s3(S3, base_st) as s0:
            dst_crs = s0.crs
            dst_res = (abs(s0.transform.a), abs(s0.transform.e))
            aoi_dst = transform_geom("EPSG:4326", dst_crs.to_string(), aoi, precision=6)
            aoi_bounds = feat_bounds(aoi_dst)

        # 1) Thermal mosaic (DN) on destination grid – merges all scenes for the day
        st_vrts, keep = [], []
        try:
            for r in recs:
                u = pick_st_from_row(r)
                if not u or not s3_head_exists(S3, u):
                    continue
                src = gdal_open_from_s3(S3, u); keep.append(src)
                v = WarpedVRT(
                    src,
                    dst_crs=dst_crs,
                    resampling=Resampling.bilinear,
                    transform=None,
                    resolution=dst_res,
                    nodata=np.nan,
                    add_alpha=False
                )
                st_vrts.append(v)

            if not st_vrts:
                print("×", mdate, "ST not opened")
                continue

            st_dn, st_transform = merge(st_vrts, bounds=aoi_bounds, nodata=np.nan, dtype="float32")
            prof = st_vrts[0].profile.copy()
            prof.update({
                "driver":"GTiff",
                "height":st_dn.shape[1],
                "width":st_dn.shape[2],
                "count":1,
                "dtype":"float32",
                "crs":dst_crs,
                "transform":st_transform,
                "nodata":np.nan,
                "compress":"DEFLATE",
                "predictor":3,
                "zlevel":6,
                "tiled":True,
                "blockxsize":512,
                "blockysize":512
            })
        finally:
            close_quietly(st_vrts)
            close_quietly(keep)

        # 2) Celsius
        K = st_dn * SCALE_ST + OFFSET_ST
        C = K + K_TO_C

        # 3) QA_PIXEL mosaic on destination grid (bitwise OR)
        qa_or = np.zeros((prof["height"], prof["width"]), dtype="uint16")
        qa_vrts, keep2 = [], []
        try:
            for r in recs:
                uqa = pick_qa_from_row(r)
                if not uqa or not s3_head_exists(S3, uqa):
                    continue
                srcq = gdal_open_from_s3(S3, uqa); keep2.append(srcq)
                vq = WarpedVRT(
                    srcq,
                    dst_crs=dst_crs,
                    transform=prof["transform"],
                    width=prof["width"],
                    height=prof["height"],
                    resampling=Resampling.nearest,
                    nodata=0,
                    add_alpha=False
                )
                qa_vrts.append(vq)
                qa_or |= vq.read(1)
        finally:
            close_quietly(qa_vrts)
            close_quietly(keep2)

        # 4) Mask: water only, no clouds/shadow/snow/cirrus
        water  = bit_is_set(qa_or, BIT_WATER)
        clouds = (bit_is_set(qa_or, BIT_DILATED) |
                  bit_is_set(qa_or, BIT_CIRRUS)  |
                  bit_is_set(qa_or, BIT_CLOUD)   |
                  bit_is_set(qa_or, BIT_CSHADOW) |
                  bit_is_set(qa_or, BIT_SNOW))
        agua_limpia = water & (~clouds)

        # 5) Exact clip to AOI and apply mask
        tmp_tif = os.path.join(tmp_dir, f"__tmp__{mdate}.tif")
        with rio.open(tmp_tif, "w", **prof) as dst:
            dst.write(C[0], 1)
        with rio.open(tmp_tif) as tsrc:
            C_clip, C_transform = mask(tsrc, [aoi_dst], crop=True, nodata=np.nan)
        os.remove(tmp_tif)

        # If sizes do not match, re-adjust mask to the clip (nearest)
        if agua_limpia.shape != C_clip[0].shape:
            from skimage.transform import resize
            agua_limpia = resize(
                agua_limpia.astype(np.uint8),
                C_clip[0].shape,
                order=0,
                preserve_range=True
            ).astype(bool)

        C_water = C_clip.copy()
        C_water[0, ~agua_limpia] = np.nan

        # 6) Representative SceneID for output file name
        grp_sorted = grp.sort_values(["Row", "SceneID"])
        scene_id_repr = str(grp_sorted.iloc[0]["SceneID"]).strip()

        out_name = f"{scene_id_repr}.tif"
        out_path = os.path.join(tmp_dir, out_name)

        out_prof = prof.copy()
        out_prof.update({"transform": C_transform, "height": C_water.shape[1], "width": C_water.shape[2]})

        with rio.open(out_path, "w", **out_prof) as dst:
            dst.write(C_water[0], 1)
            dst.update_tags(
                UNITS="CELSIUS",
                FORMULA="C = DN*0.00341802 + 149.0 - 273.15",
                AOI="DELTA",
                MASK="QA_PIXEL water & no cloud/shadow/snow/cirrus",
                MATCHED_DATE=str(mdate),
                REPRESENTATIVE_SCENEID=scene_id_repr,
                SCENEIDS_USED=";".join(sorted(set(str(r["SceneID"]).strip() for r in recs)))
            )

        salidas.append(out_path)
        print(f"✓ {mdate}: {out_name} (mosaic of {len(recs)} scenes)")

    # 7) ZIP
    if salidas:
        if os.path.exists(ZIP_SALIDA):
            os.remove(ZIP_SALIDA)
        with zipfile.ZipFile(ZIP_SALIDA, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            for p in salidas:
                zf.write(p, arcname=os.path.basename(p))
        print("ZIP created:", ZIP_SALIDA)
    else:
        print("No outputs were generated.")
finally:
    try:
        shutil.rmtree(tmp_dir)
    except Exception:
        pass


# --- 8-bit paletted copy with a CVD-safe ramp (cividis) ---
def save_paletted_copy(tif_path, cmap_name="cividis"):
    import matplotlib.cm as cm
    import rasterio as rio
    import numpy as np

    with rio.open(tif_path) as src:
        a = src.read(1, masked=True).astype("float32")
        # "Dramatic" stretch: 2–98 percentiles
        vmin = float(np.nanpercentile(a, 2))
        vmax = float(np.nanpercentile(a, 98))
        if vmax <= vmin:
            vmin = float(np.nanmin(a)); vmax = float(np.nanmax(a))
        arr = np.clip((a - vmin) / max(vmax - vmin, 1e-6), 0, 1)
        arr8 = (arr * 255).astype("uint8")

        prof = src.profile.copy()
        prof.update(dtype="uint8", nodata=0)

        out_pal = tif_path.replace(".tif", f"_{cmap_name}_pal8.tif")
        with rio.open(out_pal, "w", **prof) as dst:
            dst.write(arr8, 1)
            lut = (cm.get_cmap(cmap_name, 256)(np.arange(256))[:, :3] * 255).astype(np.uint8)
            dst.write_colormap(1, {i: tuple(map(int, lut[i])) for i in range(256)})
            dst.update_tags(RENDER_MIN=vmin, RENDER_MAX=vmax, COLORMAP=cmap_name, NOTE="paletted_copy")
    return out_pal


# In[ ]:




