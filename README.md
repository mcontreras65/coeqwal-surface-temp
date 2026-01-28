# Coeqwal – Delta Surface Temperature Pipeline (Landsat C2 L2, S3-only)

This repository contains the working pipeline used to:
1) build a daily Dayflow + Water-Year-Type (WYT) table,
2) select target dates by NDOI/WYT criteria,
3) discover Landsat Collection 2 Level-2 scenes directly from the USGS `usgs-landsat` S3 bucket (Requester Pays),
4) generate per-date surface temperature mosaics (Celsius) clipped to the legal Delta AOI.

## Status
Work-in-progress. Next steps include expanded documentation, dependency pinning, and packaging.

## Repository contents
- `surface_temp_coeqwal_final.ipynb` — end-to-end pipeline notebook (recommended entry point)
- `surface_temp_coeqwal_final.py` — script export of the notebook (same logic, easier to review)
- `utils_s3_rasterio.py` — shared S3 + Rasterio/GDAL helper functions
- `.gitignore` — excludes `inputs/`, `outputs/`, rasters, and other artifacts from version control

## Data & privacy
This repository does **not** commit `inputs/`, `outputs/`, intermediate rasters, or other generated products. Those remain on the server environment.

## Run order (chunks)
1) Dayflow merge (1929–2024) → `outputs/dayflow_1929_2024.csv`
2) WYT download + daily join → `outputs/dayflow_wyt_daily.csv`
3) Interactive filter → `inputs/target_dates.csv`
4) S3-only Landsat scene catalog → `outputs/scene_catalog_s3only.csv`
5) Mosaics (Celsius, clipped to AOI) → `outputs/mosaicos/*.zip`

## How to run (server workflow)
This workflow is designed to run in the EASI/CSIRO Jupyter environment where AWS access is already configured.

1) Open `surface_temp_coeqwal_final.ipynb`
2) Run chunks in order (1 → 7)
3) Outputs are written to local `outputs/` and are not committed to GitHub

## Requirements
Python packages used include: `boto3`, `numpy`, `pandas`, `rasterio`, `shapely`, `requests` 

## AWS / S3 access notes
- Bucket: `usgs-landsat` (**Requester Pays**)
- Region expected: `us-west-2`
- Credentials must be available in the runtime environment (server-side)
