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
terrascope.cmd fetch-data   :: India boundary (~46 MB) + place-search index (~20 MB download, ~200 MB built), first run only
terrascope.cmd fetch-data tamil-nadu   :: optional regional cache (any state/UT slug; --list shows them)
terrascope.cmd start        :: starts all four services, waits for health, opens http://localhost:5173
terrascope.cmd status
terrascope.cmd stop
terrascope.cmd seed-demo    :: optional: one FIXTURE report for UI checks
```

**Coverage: all of India.** Every state and union territory is accepted, including
Puducherry and the other UTs. A parcel is rejected, before any evidence is collected, only
when it lies outside India (more than 1% of its area beyond the boundary). The boundary is
geoBoundaries gbOpen IND ADM1 (DataMeet India / Election Commission of India, CC BY 2.5 IN).
It is not a Survey of India boundary, and its coastline and borders are generalised. A parcel
crossing a state border lists every state it touches, with its share.

**What works everywhere in India, with no regional download:**

- Sentinel-2 land cover.
- JRC river flood hazard maps.
- JRC Global Surface Water.
- Copernicus DEM elevation.

These rasters are read remotely, window by window. River-flood results and Sentinel-2 scene
measurements are cached per parcel; other remote reads are not yet cached.

**What needs a regional cache** (`fetch-data <region>`):

- accessibility (roads, schools, hospitals, bus, rail)
- distances to rivers, canals and tanks
- elevation relative to the nearest mapped water

Without a regional cache, those layers say so and give the install command. The other
collectors still run. Nothing India-wide is downloaded automatically. A region build checks
disk space and reuses any extract and tiles already on disk.

| Data (`data-cache\`) | Source and licence | Used for |
|---|---|---|
| `india\` | geoBoundaries IND ADM1, CC BY 2.5 IN | coverage check, state attribution |
| `regions\<slug>\osm.sqlite` | OpenStreetMap via the Geofabrik India zone extract, ODbL 1.0 | accessibility; rivers, canals, tanks |
| `rasters\gsw\` | JRC Global Surface Water v1.4 (1984-2021), Copernicus, "Source: EC JRC/Google" | surface water seen inside the parcel and within 500 m |
| `rasters\dem\` | Copernicus DEM GLO-30 via Planetary Computer, Copernicus DEM licence | elevation; height above the nearest mapped water |
| `flood-hazard\` | JRC global river flood hazard maps v2.1.2, CC BY 4.0 (doi:10.2905/JRC.VD32YWG) | tile index and cached per-parcel results |
| `places\places.sqlite` | GeoNames gazetteer and postal codes for India, CC BY 4.0 (credit GeoNames) | search suggestions while typing (no web geocoder is called while typing) |
| `satellite\sentinel2-cache.sqlite` | derived from Sentinel-2 L2A (Planetary Computer) | reused scene measurements (immutable) and catalogue searches (refreshed after 6 h for recent windows) |
| `valuation\observations.csv` | yours: licensed or permitted price observations (none today) | comparable-based price ranges |

**Flood evidence is reported per mechanism, with no overall score.** The mechanisms are:

- modelled river flooding by return period (1-in-10 to 1-in-500 years, ~90 m)
- observed surface water
- terrain and nearby water
- rainfall/waterlogging and coastal flooding, which are not assessed

Flood Safety stays unscored until a combining method is validated. Overpass is used only
when `OSM_OVERPASS_FALLBACK=true` and no regional store is installed.

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

- **Satellite:** none needed. Sentinel-2 comes from Planetary Computer without an account;
  AppEEARS is used only if `NASA_APPEEARS_*` credentials are set.
- **AI explanations:** `GROQ_API_KEY`. Without it the report shows the rule-based
  "Assessment summary", which still cites the evidence rows behind each figure, and uploaded
  documents are still searched for the survey number and village you enter (cited by page).
  The label says "AI explanation" only when an AI call actually succeeded.

RERA evidence additionally needs a seed CSV — see
[data-pipeline/data/raw/README.md](data-pipeline/data/raw/README.md).

The Compose stack is for local demo use only. Service-to-service URLs use Compose service names such as `http://data-pipeline:8001` and `http://ml-models:8002` inside the network.


## Land valuation

The report shows a **listing-based estimated price range** (or a sale-based one, or a government
guideline value) computed only from comparable prices: nearby, recent, similar-size vacant land of the same
use. Asking prices, sale prices and guideline values are never pooled, and the spread shown is the
comparables' own spread, not a validated prediction interval. The price is independent of suitability
weights, flood and legal evidence.

**No permitted price data is loaded today, so every parcel gets "No price estimate".** Owner/broker-supplied or
licensed rows can be imported from "Price data" on the start page (preview with per-row reasons, then commit).
The sources checked, their verified reuse terms and the smallest input that would unlock a real estimate are in
[docs/SETUP_VALUATION.md](docs/SETUP_VALUATION.md). The data contract, cleaning, estimator and the
prediction-quality harness (`python -m valuation.evaluate`) are in [valuation/README.md](valuation/README.md).
Prediction quality: **not yet validated**.

## What the evidence does and does not claim

- **RERA** — the seed dataset matches on *district only*. A match means some
  registered project shares the parcel's district; it is never treated as proof
  that this parcel is registered, so `rera.is_rera_project` stays `null`
  (unknown) and the match is recorded as candidate evidence.
- **Land records** — there is no land-records connector, so title and
  encumbrance are unknown, and the scoring treats unknown as unverified rather
  than as safe. You can record survey details (state, district, taluk, village,
  survey and subdivision numbers) and typed documents (patta, EC, sale deed,
  approvals) on the report; they stay "user-provided, not verified" and never
  produce a legal score.
- **Accessibility** — straight-line distances to OpenStreetMap geometry, from the
  drawn boundary (and from the centroid, shown alongside). Your road and school
  distance limits set where each sub-score reaches 0. Proximity is not legal access.
- **Satellite change** — one Sentinel-2 scene per season anchor across the whole
  window, compared same season against same season a year apart. The result is
  "no material change", a change class, or "inconclusive", with no confidence
  percentage (the rule thresholds are not calibrated).
- **Measured vs scored** — "measured" counts the evidence fields collected for
  the parcel; "scored" is the share of your weighting backed by a factor score.
  They answer different questions, and the report shows both with their
  denominators.

## Contributing

Work is organized by track. Create a branch for the area you are changing: `data-integration`, `ml-pipeline`, or `frontend-ui`. Keep commits focused, open a pull request from the track branch into `main`, and wait for review before merging. Cross-track changes should still have a clear primary track and call out any coordination needs in the pull request description.

