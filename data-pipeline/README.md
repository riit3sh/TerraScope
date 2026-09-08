# TerraScope Data Pipeline

This service performs the blocking first-pass evidence collection for one user-defined parcel. It stores the resulting snapshot as immutable evidence; investor profile, weights, property type, horizon, and preferences are evaluated later and do not call this service again.

## Run Locally

From `data-pipeline/`:

```bash
python -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
uvicorn internal_api:app --host 0.0.0.0 --port 8001 --reload
```

Required environment variables:

- `DATABASE_URL` — PostgreSQL/PostGIS connection string.
- `SATELLITE_PROVIDER` — use `appeears` for NASA AppEEARS (the local default), or `cdse` for the legacy Copernicus connector.
- `NASA_APPEEARS_USERNAME` and `NASA_APPEEARS_PASSWORD` — Earthdata Login credentials for AppEEARS. Prefer these for the demo. `NASA_APPEEARS_TOKEN`, if used, must be the token returned by AppEEARS `/api/login`; a generic Earthdata/URS token is not interchangeable.
- `NASA_APPEEARS_PRODUCT`, `NASA_APPEEARS_B04_LAYER`, `NASA_APPEEARS_B08_LAYER`, and `NASA_APPEEARS_B11_LAYER` — AppEEARS catalog values for the HLS product and red/NIR/SWIR layers.
- `NOMINATIM_USER_AGENT` — descriptive User-Agent for explicit geocoding/reverse-geocoding.

Optional environment variables:

- `RERA_SEED_PATH` — path to `maharera_seed.csv`; defaults to `data/raw/maharera_seed.csv`.
- `REGIONAL_BASELINE_ELEVATION_M` — baseline used by the coarse flood-risk proxy; defaults to the sampled representative elevation.
- `TERRASCOPE_OSM_CACHE_PATH` and `TERRASCOPE_OSM_USER_AGENT` — local OSM cache/User-Agent overrides.
- `NASA_APPEEARS_POLL_SECONDS` and `NASA_APPEEARS_MAX_WAIT_SECONDS` — asynchronous task polling controls.
- `TERRASCOPE_SATELLITE_CACHE_PATH` — JSON cache for identical polygon/date/product requests.

The repository Compose stack starts this API on port `8001` and initializes PostGIS. The build call is intentionally blocking for the demo and can take time while satellite, OSM, elevation, and RERA evidence are collected.

## Build Evidence Snapshot

```bash
curl -X POST http://localhost:8001/internal/analysis/build \
  -H "Content-Type: application/json" \
  -d '{
    "polygon": {
      "type": "Polygon",
      "coordinates": [[[73.8567,18.5204],[73.8582,18.5204],[73.8582,18.5218],[73.8567,18.5218],[73.8567,18.5204]]]
    },
    "date_from": "2024-01-01",
    "date_to": "2024-12-31",
    "address": "Pune, Maharashtra"
  }'
```

## Read Evidence Snapshot

Replace the id with `metadata.analysis_snapshot_id` from the build response:

```bash
curl http://localhost:8001/internal/analysis/<snapshot_id>
```
