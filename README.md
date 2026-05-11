# COEQWAL — Delta Water Quality Pipelines

Satellite-based pipelines for retrieving water quality variables over the California Legal Delta, developed in support of the [COEQWAL project](https://coeqwal.org) (Collaboratory for Equity in Water Allocations).

---

## Pipelines

### 1. Land Surface Temperature — `coeqwal_delta_surface_temp_pipeline.ipynb`
Retrieves Land Surface Temperature (LST) over the Legal Delta from Landsat 4/5/7/8/9 imagery via Open Data Cube (ODC). Target dates are selected based on hydrological conditions — specifically Net Delta Outflow Index (NDOI) from Dayflow and Water Year Type (Wet, Above Normal, Below Normal, Dry, Critical) for the Sacramento and San Joaquin valleys. Output is one cloud-masked, mosaicked GeoTIFF per target date in degrees Celsius (UTM Zone 10, 30 m resolution).

### 2. Water Turbidity — `delta_turbidity_landsat_sentinel2_pipeline.ipynb`
Retrieves water turbidity over the Legal Delta from Landsat 8/9 and Sentinel-2 A/B/C imagery using the Dogliotti et al. (2015) switching model applied to ACOLITE Aquatic Reflectance C4 products. Output is one GeoTIFF per target date in Formazin Turbidity Units (FTU, float32).

---

## Configuration

Each pipeline reads from a YAML config file:
- `config.yaml` — LST pipeline settings (AOI, resolution, WRS tiles, cloud cover, sensor preference)
- `config_turbidity.yaml` — Turbidity pipeline settings (MGRS tiles, Dogliotti parameters, masking thresholds)

To use a custom config: `python pipeline.py --config other_config.yaml`

---

## Requirements

Both pipelines run on the CSIRO Open Data Cube (ODC) JupyterHub environment. Dependencies include: `datacube`, `geopandas`, `xarray`, `rioxarray`, `rasterio`, `numpy`, `pandas`, `pyyaml`.

---

## Project Context

COEQWAL is a $9.1M UC-led project exploring equitable water allocation in California under climate change. These pipelines support the salmon recovery and drinking water use cases by providing reproducible, condition-linked water quality observations over the Sacramento-San Joaquin Delta.
