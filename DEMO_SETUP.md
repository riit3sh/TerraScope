# TerraScope Local Demo Setup

TerraScope Review 2 runs entirely from a laptop. There are no Render, Vercel, or other cloud deployment configurations in this pass.

## Start From A Clean Clone

1. Copy the example environment file and add local credentials:

   ```powershell
   Copy-Item .env.example .env
   ```

2. Edit `.env` with real local API keys. Keep `.env` uncommitted; it is covered by the root `.gitignore`.

   Grounded explanations use Groq. Set `GROQ_API_KEY` and optionally `GROQ_MODEL`.

   Satellite evidence uses NASA AppEEARS by default. Set `NASA_APPEEARS_USERNAME` and
   `NASA_APPEEARS_PASSWORD` to your Earthdata Login credentials, or set
   `NASA_APPEEARS_TOKEN` if your AppEEARS setup provides a token. Confirm the HLS
   product/layer names in the AppEEARS catalog and update the `NASA_APPEEARS_*_LAYER`
   values if needed.

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

### Explicit Nominatim search

Nominatim is called only after the user submits the address search form. There is no autocomplete and no request per keystroke. The browser-side search result should be treated as the explicit geocoding request for that parcel; repeated searches should use the application’s cached/local result rather than issuing a request on every input event.

### Satellite evidence reuse

The AppEEARS client caches results using the polygon hash, date range, product, and
layer parameters. Repeat an analysis with the identical GeoJSON polygon and identical
date interval to confirm the cached satellite evidence is reused and the external
archive is not reprocessed.

## Stop The Demo

Use `Ctrl+C` in the Compose terminal. The PostGIS volume is named `postgres-data`, so ordinary restarts preserve the local database. Remove it only when intentionally resetting the demo dataset.
