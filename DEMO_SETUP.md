# TerraScope Local Demo Setup

TerraScope Review 2 runs entirely from a laptop. There are no Render, Vercel, or other cloud deployment configurations in this pass.

## Start From A Clean Clone

1. Copy the example environment file and add local credentials:

   ```powershell
   Copy-Item .env.example .env
   ```

2. Edit `.env` with real local API keys. Keep `.env` uncommitted; it is covered by the root `.gitignore`.

   Grounded explanations use Groq. Set `GROQ_API_KEY` and optionally `GROQ_MODEL`.

   Satellite evidence uses Microsoft Planetary Computer by default. It reads real
   Sentinel-2 L2A imagery without a satellite API key. NASA AppEEARS is optional:
   set `SATELLITE_PROVIDER=appeears` only after verifying your Earthdata login,
   token, product, and layer names.

3. Start the complete stack from the repository root:

   ```powershell
   docker-compose up --build
   ```

4. Open [http://localhost:5173](http://localhost:5173). The services are exposed locally at:

   - Frontend: `http://localhost:5173`
   - Backend API: `http://localhost:8000`
   - Data pipeline: `http://localhost:8001`
   - ML models: `http://localhost:8002`
   - PostGIS: `localhost:5432`

Inside Compose, the backend calls `http://data-pipeline:8001` and `http://ml-models:8002` by service name. The browser calls the backend through `http://localhost:8000`.

## Pre-Demo Checklist

- Confirm `.env` contains real API keys locally and that no secrets are committed.
- Run one complete end-to-end parcel analysis before the Review 2 slot.
- Change at least one scenario assumption after the initial analysis and confirm the verdict updates without recollecting evidence.
- Upload a PDF evidence document and verify the upload/indexing state.
- Keep a pre-recorded backup video of a successful run available in case a public data provider is unavailable.

## Demo Contracts To Verify

### Map attribution

The parcel workspace uses Leaflet with OpenStreetMap tiles and keeps the OpenStreetMap attribution visible in the map control. Do not crop or hide the attribution during the demo.

### Nominatim search and suggestions

Search suggestions are debounced by 650 ms, cached in the browser and backend, restricted to India, and guarded to one uncached Nominatim request per second. The main demo path is tuned for Tamil Nadu locations such as Vellore and Chennai. Selecting a suggestion reuses its coordinates and opens the parcel workspace without a second geocoding request.

### Satellite evidence reuse

The configured satellite provider caches scene/catalogue reads using the polygon,
date range, and provider parameters. JRC surface-water and Copernicus DEM parcel
results also use a 30-day on-disk cache. Repeat an analysis with the identical
GeoJSON polygon and identical date interval to reuse evidence instead of reprocessing
the external archive.

### Tamil Nadu readiness

For the best local results around Vellore and Chennai, install the India boundary and
Tamil Nadu regional OSM/DEM/water cache before the demo:

```powershell
terrascope.cmd fetch-data tamil-nadu
```

This is a one-time download/build step and can take several minutes. The first
analysis can still take roughly 10-20 seconds because remote satellite scenes may be
read. Repeating the exact parcel and date range should be much faster after caches
are warm. No honest configuration can guarantee seconds for a first live analysis
while public providers are still downloading data.

## Stop The Demo

Use `Ctrl+C` in the Compose terminal. The PostGIS volume is named `postgres-data`, so ordinary restarts preserve the local database. Remove it only when intentionally resetting the demo dataset.
