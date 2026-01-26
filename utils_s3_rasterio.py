# utils_s3_rasterio.py
# Shared helpers for S3 + Rasterio/GDAL workflows (Requester Pays)

import os
import json as _json
import tempfile
from urllib.parse import urlparse

import rasterio as rio
from shapely.geometry import shape, mapping
import boto3
from botocore.config import Config
from botocore.exceptions import ClientError


def configure_aws_gdal_env(region: str = "us-west-2", requester_payer: str = "requester") -> None:
    os.environ.setdefault("AWS_REGION", region)
    os.environ["AWS_REQUEST_PAYER"] = requester_payer
    os.environ.setdefault("GDAL_DISABLE_READDIR_ON_OPEN", "EMPTY_DIR")
    os.environ.setdefault("AWS_S3_ENDPOINT", f"s3.{region}.amazonaws.com")


def make_s3_client(region: str | None = None):
    region = region or os.environ.get("AWS_REGION", "us-west-2")
    return boto3.client("s3", region_name=region, config=Config(signature_version="s3v4"))


def s3_to_bucket_key(s3_url: str):
    if not isinstance(s3_url, str) or not s3_url.startswith("s3://"):
        return None, None
    p = urlparse(s3_url)
    return p.netloc, p.path[1:] if p.path.startswith("/") else p.path


def s3_head_exists(s3_client, s3_url: str, requester_payer: str = "requester") -> bool:
    bkt, key = s3_to_bucket_key(s3_url)
    if not bkt or not key:
        return False
    try:
        s3_client.head_object(Bucket=bkt, Key=key, RequestPayer=requester_payer)
        return True
    except ClientError:
        return False


def gdal_open_from_s3(s3_client, s3_url: str, requester_payer: str = "requester"):
    bkt, key = s3_to_bucket_key(s3_url)
    if not bkt or not key:
        raise rio.errors.RasterioIOError(f"Invalid S3 URL: {s3_url}")

    for vsi in (f"/vsis3/{bkt}/{key}", f"/vsis3_streaming/{bkt}/{key}"):
        try:
            return rio.open(vsi)
        except Exception:
            pass

    try:
        presigned = s3_client.generate_presigned_url(
            ClientMethod="get_object",
            Params={"Bucket": bkt, "Key": key, "RequestPayer": requester_payer},
            ExpiresIn=3600,
        )
        return rio.open(f"/vsicurl/{presigned}")
    except Exception:
        pass

    tmp = tempfile.NamedTemporaryFile(suffix=".tif", delete=False)
    tmp_path = tmp.name
    tmp.close()
    try:
        s3_client.download_file(bkt, key, tmp_path, ExtraArgs={"RequestPayer": requester_payer})
        return rio.open(tmp_path)
    except Exception as e:
        try:
            os.remove(tmp_path)
        except Exception:
            pass
        raise rio.errors.RasterioIOError(f"Could not open {s3_url}: {e}")


def load_aoi_geojson(path_geojson: str):
    with open(path_geojson, "r", encoding="utf-8") as f:
        gj = _json.load(f)

    if gj.get("type") == "FeatureCollection":
        geoms = [shape(feat["geometry"]) for feat in gj["features"]]
        g = geoms[0]
        for h in geoms[1:]:
            g = g.union(h)
        return mapping(g)

    if gj.get("type") == "Feature":
        return gj["geometry"]

    return gj


def pick_first_s3(row: dict, cols: list[str]):
    for c in cols:
        v = row.get(c)
        if isinstance(v, str) and v.startswith("s3://"):
            return c, v
    return None, None


def close_quietly(objs):
    for o in objs:
        try:
            o.close()
        except Exception:
            pass
