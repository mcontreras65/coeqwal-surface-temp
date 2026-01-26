# Delta Surface Temperature Pipeline (Landsat C2 L2, S3-only)

This repository contains the working pipeline used to:
1) build a daily Dayflow + Water-Year-Type (WYT) table,
2) select target dates by NDOI/WYT criteria,
3) discover Landsat Collection 2 Level-2 scenes directly from the USGS `usgs-landsat` S3 bucket (Requester Pays),
4) generate per-date surface temperature mosaics (Celsius) clipped to the legal Delta AOI.

## Status
Work-in-progress. This is a first professional snapshot for review; documentation and packaging will be expanded next.

## Key files
- `surface_temp_coeqwal_final.ipynb` — end-to-end pipeline notebook
- `utils_s3_rasterio.py` — S3 + Rasterio/GDAL helper functions

## Notes
- AWS access is Requester Pays (`usgs-landsat`).
