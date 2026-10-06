# TerraScope

TerraScope is a local-first geospatial intelligence platform for land due diligence. You search a place, draw the parcel boundary, and it collects one immutable evidence snapshot — satellite NDVI/NDBI change, OpenStreetMap infrastructure distances, centroid elevation, RERA seed matches, and any documents you upload — then evaluates that fixed snapshot against your investor profile to produce a BUY / WAIT / AVOID verdict with visible weights and citations.

Collection and evaluation are deliberately separate: moving a slider or switching profiles re-runs only the fast evaluation layer and never re-collects evidence. See [docs/architecture.md](docs/architecture.md).

## Folder Structure

```text
terrascope/
├── docs/schema/                    # Shared data and API schema notes
├── data-pipeline/                  # Data ingestion package and connectors
│   ├── connectors/
│   ├── db/
│   └── src/terrascope_data_pipeline/
├── ml-models/                      # ML service package and model areas
│   ├── change_detection/
│   ├── rag_pipeline/
│   ├── scoring_engine/
│   └── src/terrascope_ml_models/
├── backend-api/                    # Public API package
│   ├── routers/
│   └── src/terrascope_backend_api/
├── valuation/                      # Land-price import, training and prediction
│   ├── fixtures/                   # SYNTHETIC demo data (never real evidence)
│   └── artifacts/                  # Trained model + metadata
├── frontend/                       # Vite + React + TypeScript + Tailwind app
├── tests/integration/              # Black-box tests against a running stack
├── scripts/smoke_test.sh           # Checks every service is reachable
├── docker-compose.yml              # Local development services
├── .env.example                    # Placeholder environment variables
└── README.md
```

## Local Development

### Native Windows (no Docker)

Needs Python 3.11 (`py -3.11`) and Node.js. From the repository root:

```bat
copy .env.example .env      :: then blank DATABASE_URL and any placeholder keys
terrascope.cmd setup        :: .venv + pip requirements + npm ci (first run only)
terrascope.cmd fetch-data   :: local Tamil Nadu data, ~2.5 GB into tn-data\ (first run only)
terrascope.cmd start        :: starts all four services, waits for health, opens http://localhost:5173
terrascope.cmd status
terrascope.cmd stop
terrascope.cmd seed-demo    :: optional: one FIXTURE report for UI checks
```

TerraScope covers **Tamil Nadu only**. Parcels outside it, or in the Puducherry/Karaikal
enclaves, get an "outside coverage" answer and no evidence is collected. `fetch-data`
builds what analyses read from disk:

| Data | Source and licence | Used for |
|---|---|---|
| `tn_osm.sqlite`, `tn_boundary.geojson` | OpenStreetMap via the Geofabrik southern-zone extract, ODbL 1.0 | coverage check; roads, schools, hospitals, bus, rail; rivers, canals, tanks |
| `gsw/` | JRC Global Surface Water v1.4 (1984-2021), Copernicus, "Source: EC JRC/Google" | surface water seen inside the parcel and within 500 m |
| `dem/` | Copernicus DEM GLO-30 via Planetary Computer, Copernicus DEM licence | parcel elevation; height above the nearest mapped water |

`manifest.json` in `tn-data\` records each dataset's date and size. Overpass is used only
when `OSM_OVERPASS_FALLBACK=true` and the local store is missing. Flood indicators are
evidence only: Flood Safety stays unscored.

`start` reuses a port only when it already serves the healthy TerraScope service.
It refuses ports held by anything else, and `stop` only stops processes started from
this folder. Saved reports persist in `.local-ui-check\backend.sqlite3`, and logs go to
`.local-ui-check\logs`. PostGIS is not used natively: the data-pipeline's spatial archive
is skipped, and the backend still stores every snapshot.

### Docker Compose

1. Copy `.env.example` to `.env` and adjust values for your local environment if needed.
2. Start the local stack:

   ```bash
   docker-compose up --build
   ```

3. Open the frontend at [http://localhost:5173](http://localhost:5173). The service endpoints are available at `http://localhost:8000`, `http://localhost:8001`, and `http://localhost:8002`.

4. Confirm the stack is healthy and exercise it end to end:

   ```bash
   bash scripts/smoke_test.sh
   pytest tests/integration -v
   ```

   Unit tests need no running stack:

   ```bash
   pytest valuation/test_valuation.py ml-models/test_retrieval_cache.py -v
   ```

The first build downloads a CPU build of PyTorch for the RAG embeddings, so
expect it to take several minutes on a slow connection.

### What needs credentials

The stack runs without any keys, but two evidence layers stay empty until you
supply them in `.env`:

- **Satellite (NDVI/NDBI charts):** `NASA_APPEEARS_USERNAME` / `NASA_APPEEARS_PASSWORD`.
  Without them the report honestly reports `insufficient_evidence` and plots nothing.
- **Grounded explanations and citations:** `GROQ_API_KEY`. Without it the verdict
  falls back to the deterministic rule-based summary.

RERA evidence additionally needs a seed CSV — see
[data-pipeline/data/raw/README.md](data-pipeline/data/raw/README.md).

The Compose stack is for local demo use only. Service-to-service URLs use Compose service names such as `http://data-pipeline:8001` and `http://ml-models:8002` inside the network.


## Land valuation

The report shows an estimated price per sq ft and total land value alongside the
suitability verdict. The two are computed independently on purpose: **changing a
priority slider re-scores suitability and cannot move the market price.**

**The repository ships no real price data.** The import, training, serving and UI
path is complete and tested, but out of the box it runs on a clearly labelled
synthetic fixture, and every prediction from it is stamped `is_synthetic` and
banner-labelled DEMO DATA in the UI. To get real numbers:

```bash
python -m valuation.train path/to/land_prices.csv --out valuation/artifacts/land_price_model.joblib
```

The CSV contract, the minimum dataset requirements and the refusal reasons are in
[valuation/README.md](valuation/README.md). A parcel outside the data's coverage
gets an explicit "unavailable" with the reason, never a guessed number.

## What the evidence does and does not claim

- **RERA** — the seed dataset matches on *district only*. A match means some
  registered project shares the parcel's district; it is never treated as proof
  that this parcel is registered, so `rera.is_rera_project` stays `null`
  (unknown) and the match is recorded as candidate evidence.
- **Land records** — there is no land-records connector, so title and
  encumbrance are unknown, and the scoring treats unknown as unverified rather
  than as safe.
- **Data completeness** counts the evidence fields actually collected, so it
  legitimately reads below 100%.

## Contributing

Work is organized by track. Create a branch for the area you are changing: `data-integration`, `ml-pipeline`, or `frontend-ui`. Keep commits focused, open a pull request from the track branch into `main`, and wait for review before merging. Cross-track changes should still have a clear primary track and call out any coordination needs in the pull request description.

