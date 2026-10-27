# TerraScope

TerraScope is a local-first land due-diligence tool for India. You search a place, draw the plot, and it collects one
immutable evidence snapshot, then answers one question for a buyer: **BUY, WAIT or WALK AWAY**.
The report is evidence-first: it separates measured observations, mapped warnings and official checks that still need
to be performed. An optional Groq call explains the already-computed result; it never creates scores or fills missing
land records.

**What the snapshot holds:**
- the area's development history (built-up land around the plot, 2017-2023);
- Sentinel-2 change on the plot;
- straight-line distances to mapped roads, schools, hospitals and transport;
- river-flood model results, observed surface water, and terrain relative to mapped water;
- mapped public facilities touching the plot;
- optional survey identifiers and recorded legal checks.

Every finding names its source and date. Missing data is reported as unknown, never as a clean result.

Collection and evaluation are separate. Changing your priorities re-runs only the fast, deterministic evaluation, never
the collection. See [docs/architecture.md](docs/architecture.md).

**Stack:**

| Service | Port | Role |
|---|---|---|
| React + TypeScript + Vite frontend (Leaflet maps) | 5173 | Map, drawing, reports |
| FastAPI `backend-api` | 8000 | API; saved reports in SQLite |
| FastAPI `data-pipeline` | 8001 | Evidence collection: OpenStreetMap stores, rasters, remote services |
| FastAPI `ml-models` | 8002 | Scoring, findings and the decision (rule-based; an optional AI summary only explains it) |

Runs natively on Windows (`terrascope.cmd`); Docker Compose is optional.

## Decision logic (rule by rule: [docs/DECISION_RULES.md](docs/DECISION_RULES.md))

Each rule is checked in order, and the first that applies decides:

1. **WALK AWAY** if any of these hold; no score can override them:
   - a matched record or your recorded check shows a legal defect (unclear title, an encumbrance, non-transferable
     government land, a prohibiting restriction);
   - a verified red flag: modelled river flooding over a quarter of the plot at 1-in-100 years or more often, or open
     water seen on the plot in at least 10 % of satellite passes.
2. **WAIT** when a weighted location factor (area growth, accessibility) has no evidence: never BUY on missing data,
   and the summary names what could not be measured. No score is shown. (Until 2026-10-27 this was a separate
   INSUFFICIENT DATA answer; saved reports with that code now read as WAIT.)
3. **BUY** when the location score is at least 75 (strong access and a developing area). Unless matched official
   records verify title, encumbrance, zoning and approvals, it is **BUY only after the legal checks**: they are listed
   first and are never treated as done, and a defect found in them is WALK AWAY.
4. **WAIT** otherwise. The report names what holds it back and what would change the answer.
   - A mapped overlap with public land, conflicting records or a conditional restriction always holds the answer at
     WAIT, with the warning first.
5. **VERIFY RESTRICTION** when the boundary materially overlaps mapped defence, railway, water-body, court or other
   restricted land: purchase scoring is blocked until the boundary and official records are checked. This is a map
   signal, not proof of ownership or a legal restriction.

**Development history:** the report uses the measured 2017-2023 built-up trend within 1 km (and, where available,
the 1-3 km ring). It describes past modelled land cover, not prices, approvals or guaranteed future construction.
Every report states that TerraScope's answer is an estimate, not perfect, and not legal or financial advice.

## Data and coverage (all 28 states and 8 UTs: [docs/DATASET_REGISTRY.md](docs/DATASET_REGISTRY.md))

Every cell of the registry is tested at a sample point in each region (`python data-pipeline/dataset_registry.py`).

| Layer | Coverage |
|---|---|
| Boundaries and region resolution (geoBoundaries), place search (GeoNames) | All 36 regions |
| Schools, hospitals, bus and rail, water bodies, waterways, public facilities (OpenStreetMap, Geofabrik India extract of 2026-10-25) | All 36 regions (all-India store; TN, PY and AP use their own stores) |
| Roads (OpenStreetMap) | Tamil Nadu, Puducherry and Andhra Pradesh only. Elsewhere roads are "not installed (unknown)" and accessibility is not assessed |
| Land cover 2017-2023, Sentinel-2, JRC river flood maps, JRC surface water, Copernicus DEM | All of India, read from public services (local tiles for TN, PY and AP) |
| Land records, EC, zoning, approvals, RERA, poramboke status | Manual checks only (Tamil Nadu guide); none automated |

Files, sizes, licences and dates are in [docs/DATASETS.md](docs/DATASETS.md). Official-record sources and the manual
workflow are in [docs/LEGAL_VERIFICATION.md](docs/LEGAL_VERIFICATION.md).

## Demo

Start the app (first run: `terrascope.cmd setup` and `terrascope.cmd fetch-data`):

```bat
terrascope.cmd start
```

It opens http://localhost:5173. Three plots show the range:

1. **Senjeri, Coimbatore (saved report).** Shows the Tamil Nadu store with roads, the development chart, and WAIT
   with the legal checks pending. Click "Re-evaluate with current methods": this adds one evaluation, and the old one
   is kept.
2. **Mamillapalli, Kadapa (saved report).** The boundary overlaps 97 % of the mapped YS Raja Reddy Cricket Stadium.
   The answer is WAIT, with a warning that this is a potential spatial overlap, not an ownership finding, and the
   official poramboke check to do.
3. **Patna (draw a small plot).** Uses the all-India stores: roads, schools, hospitals, water and public facilities.

**Automated:** mapping, flood model, land-cover history and the decision rules. **Manual:** title, EC, zoning,
approvals and government-land status; you record them, and they are never automated clearance.

`terrascope.cmd stop` stops only TerraScope's own services. Saved reports stay in `.local-ui-check\backend.sqlite3`.

## Tests (run 2026-10-26)

| Suite | Command | Result |
|---|---|---|
| ML (scoring, verdict, findings) | `cd ml-models && ..\.venv\Scripts\python -m pytest -q` | 80 passed |
| Backend API | `cd backend-api && ..\.venv\Scripts\python -m pytest -q` | 29 passed |
| Data pipeline (incl. the 36-region registry) | `cd data-pipeline && ..\.venv\Scripts\python -m pytest -q` | 96 passed |
| Valuation (unused module) | `cd valuation && ..\.venv\Scripts\python -m pytest -q` | 52 passed |
| Integration (own temporary store) | `.venv\Scripts\python -m pytest -q tests/integration` | 13 passed |
| Frontend | `cd frontend && npx tsc --noEmit -p . && npm run build` | passed |

## Known limitations and future work

- **Official verification:** TerraScope has no authorised machine-readable integration for title, EC, zoning,
  approvals or poramboke status, so those checks are manual. Future work: integrate a source if one is opened,
  or obtain authorization.
- **Roads outside TN, PY and AP:** a nationwide road store needs about 3 GB more disk than the development machine
  has. Each state can be built with `terrascope.cmd fetch-data <state>`.
- **Flooding:** only modelled river flooding is assessed. Rainfall waterlogging and coastal flooding are **not
  assessed**. Flood Safety is not scored.
- **OpenStreetMap:** completeness varies widely by state, and positions can be about 15 m off. A missing feature
  is not proof of absence.
- **Imagery:** the satellite basemap (EOxCloudless) is for non-commercial use only. Bhuvan layers are viewing-only
  without written NRSC authorization and are not integrated.
- **RERA:** the report asks who is selling, opens the official authority's portal (all 36 regions, MoHUA's list) and records what the buyer found there. It is never automated. A district seed match is only candidate context, never parcel verification.
- **Local news (GDELT):** frequently rate-limited. A failed search is shown as unavailable, never as "no news".

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
│   ├── land_analyst.py            # strict, fact-only Groq explanation/Q&A
│   ├── scoring_engine/
│   └── src/terrascope_ml_models/
├── backend-api/                    # Public API package
│   ├── routers/
│   └── src/terrascope_backend_api/
├── valuation/                      # Not used in this version (land prices removed)
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

For the Vellore/Tamil Nadu demo, run `terrascope.cmd fetch-data tamil-nadu` once before starting the services.
This builds a local Tamil Nadu/Puducherry index for roads, schools, hospitals, rail, water and mapped public
facilities, plus local DEM and surface-water tiles. The cache is machine-local and is not committed to Git. Other
states can be prepared with their own slug; place search and the India-wide raster layers work without a state cache.

**What works everywhere in India:** land cover 2017-2023, Sentinel-2, JRC river flood maps, JRC surface water and
Copernicus DEM (read remotely, window by window, where no local tiles are installed); and, from the all-India store
(`python data-pipeline/fetch_data.py --national`, built from the Geofabrik India extract), schools, hospitals, bus and
rail, rivers, canals, tanks and mapped public facilities. River-flood, Sentinel-2, surface-water and DEM parcel results
are cached; failed provider reads are never cached.

**Roads:** a state store (`fetch-data <state>`) takes precedence over the all-India stores. Where a state has none,
roads come from the all-India road store (`regions/india/roads.sqlite`, `fetch_data.py --national-roads`). If neither is
installed, the report says "road data not installed (unknown)", accessibility is not assessed, and the decision is WAIT.

How the decision is made, rule by rule, is in [docs/DECISION_RULES.md](docs/DECISION_RULES.md). Nothing is downloaded
automatically; a build checks disk space and reuses any extract and tiles already on disk.

| Data (`data-cache\`) | Source and licence | Used for |
|---|---|---|
| `india\` | geoBoundaries IND ADM1, CC BY 2.5 IN | coverage check, state attribution |
| `regions\<slug>\osm.sqlite` | OpenStreetMap via a Geofabrik extract, ODbL 1.0 | roads (state stores only), schools, hospitals, transport; rivers, canals, tanks |
| `regions\<slug>\public_land.sqlite` | OpenStreetMap, ODbL 1.0 | mapped public facilities touching the plot (never ownership) |
| `regions\india\` | OpenStreetMap, Geofabrik `india-261025.osm.pbf` (MD5-verified, kept unchanged in `downloads\`), ODbL 1.0 | the all-India store: every layer above except roads |
| `rasters\gsw\` | JRC Global Surface Water v1.4 (1984-2021), Copernicus, "Source: EC JRC/Google" | surface water seen inside the parcel and within 500 m |
| `rasters\dem\` | Copernicus DEM GLO-30 via Planetary Computer, Copernicus DEM licence | elevation; height above the nearest mapped water |
| `flood-indicators-cache.json` | derived from Impact Observatory / Esri 10 m Annual Land Use Land Cover v2 (CC BY 4.0, Planetary Computer), and from JRC GSW / Copernicus DEM | per-parcel results, 30 days: land cover per year on the plot, within 1 km and 1-3 km |
| `flood-hazard\` | JRC global river flood hazard maps v2.1.2, CC BY 4.0 (doi:10.2905/JRC.VD32YWG) | tile index and cached per-parcel results |
| `places\places.sqlite` | GeoNames gazetteer and postal codes for India, CC BY 4.0 (credit GeoNames) | search suggestions while typing (no web geocoder is called while typing) |
| `satellite\sentinel2-cache.sqlite` | derived from Sentinel-2 L2A (Planetary Computer) | reused scene measurements (immutable) and catalogue searches (refreshed after 6 h for recent windows) |

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

   Unit tests need no running stack; run the relevant package tests with `pytest -q`.

The live application does not use document upload, document embeddings, or document retrieval. The Land Analyst is a
bounded Groq explanation/Q&A layer over the immutable collected snapshot; it cannot create missing evidence or verify
title, ownership, RERA, flood safety, access rights, or prices.

### What needs credentials

The stack runs without any keys, but two evidence layers stay empty until you
supply them in `.env`:

- **Satellite:** none needed. Sentinel-2 comes from Planetary Computer without an account.
  The default is `SATELLITE_PROVIDER=planetary`; AppEEARS is opt-in only when you explicitly
  set `SATELLITE_PROVIDER=appeears` and configure its credentials.
- **AI explanations:** `GROQ_API_KEY` and optional `GROQ_MODEL` (default `openai/gpt-oss-20b`). Without it the report shows the rule-based
  "Assessment summary", which still cites the evidence rows behind each figure. The label says **TerraScope Land Analyst**
  only when the Groq call actually succeeded. Existing saved reports do not
  change retroactively: re-evaluate the same evidence or run a new analysis after adding the key.

  Groq is explanation-only: it receives collected facts and evidence references, cannot change scores,
  and its response is discarded if it cites a source that was not collected. The optional Land Analyst question
  endpoint uses the same strict evidence-only policy. It never fills missing legal, environmental or ownership data.

- **Unavailable satellite data:** a provider failure produces no observation and no chart. TerraScope never
  substitutes a generated NDVI/NDBI curve for missing imagery.
- **Planetary Computer TLS errors:** certificate verification remains enabled by default. If a corporate proxy or
  antivirus inserts a trusted local CA, set `PLANETARY_CA_BUNDLE` to its PEM file. For a laptop-only demo, if the
  certificate chain cannot be repaired, `PLANETARY_TLS_VERIFY=false` allows the satellite layer to continue with an
  explicit warning; do not use that setting in production. Other evidence layers continue and the report labels
  satellite data unavailable rather than fabricating observations.

RERA evidence additionally needs a seed CSV — see
[data-pipeline/data/raw/README.md](data-pipeline/data/raw/README.md).

The Compose stack is for local demo use only. Service-to-service URLs use Compose service names such as `http://data-pipeline:8001` and `http://ml-models:8002` inside the network.

### Performance expectations

The first analysis of a new parcel can take roughly 10-20 seconds because live
satellite and raster evidence may need to be downloaded. Repeating the identical
GeoJSON polygon and date range reuses the evidence caches and should be much faster.
No live-data configuration can guarantee a few-second first run when public providers
are still responding over the network.


## Report interpretation and map providers

- **OpenStreetMap, not Google Maps:** nearby roads, schools, hospitals, rail and public-facility overlays come from
  the local OpenStreetMap/Geofabrik cache. Distances are straight-line proximity measurements, not driving routes
  and not proof of legal access. A missing OSM feature means unknown, not absent.
- **Optional Google geocoding:** set `GOOGLE_LOCATION_PROVIDER=google` and provide `GOOGLE_MAPS_API_KEY` to use
  Google's Geocoding API for the explicit Search submission. Autocomplete remains the local GeoNames index, so
  typing does not create paid requests. Google does not supply legal, ownership, RERA or environmental evidence.
- **Optional routed distance:** set `GOOGLE_ROUTES_ENABLED=true` and provide `GOOGLE_ROUTES_API_KEY` (or the same
  Maps key) to add Google driving distance/time from the parcel centroid to the nearest mapped road/school. Without
  it, the report uses exact straight-line distance to OSM geometry and labels it as such; proximity is not travel
  distance or proof of legal access.
- **Mapped restriction:** if a parcel overlaps a mapped lake, park, railway, defence area or similar feature, the
  report shows `VERIFY RESTRICTION` and blocks purchase scoring. Redraw the boundary around the actual land under
  consideration, then compare it with the seller's survey sketch/FMB and verify the survey number with official Tamil
  Nadu records. The map overlap alone is never an ownership conclusion.
- **Restricted reports still show evidence:** collected facilities, satellite evidence, the evidence ledger and the
  Land Analyst/rule-based explanation remain visible. Only purchase scoring is withheld.
- **Groq's role:** the rule engine owns the recommendation, numbers and citations. Groq receives those facts and may
  write a short explanation. It must say when evidence is unavailable and cannot invent title, RERA, flood or
  ownership results.

## Land prices: not in this version

TerraScope shows no land price, price range or placeholder value. No permitted, verified price dataset is available
(Tamil Nadu guideline values need the Registration Department's permission to reproduce; listing portals need
licences), and an unverified price would undermine every other check. Price never affects BUY / WAIT / AVOID. The
earlier comparable-price module stays, unused, in `valuation/` for a later version; the sources checked are in
[docs/SETUP_VALUATION.md](docs/SETUP_VALUATION.md).

## What the evidence does and does not claim

- **RERA** — the seed dataset matches on *district only*. A match means some
  registered project shares the parcel's district; it is never treated as proof
  that this parcel is registered, so `rera.is_rera_project` stays `null`
  (unknown) and the match is recorded as candidate evidence.
- **Land records** — there is no land-records connector, so title and
  encumbrance are unknown, and the scoring treats unknown as unverified rather
  than as safe. Checks you record (source, date, reference) are shown as yours: a recorded problem means WALK
  AWAY; a recorded confirmation is shown as yours and never counts as verification. You can record survey details (state, district, taluk, village,
  survey and subdivision numbers) on the report; they stay "user-provided, not verified" and never
  produce a legal score.
- **Accessibility** — straight-line distances to OpenStreetMap geometry, from the
  drawn boundary (and from the centroid, shown alongside). Your road and school
  distance limits set where each sub-score reaches 0. Proximity is not legal access.
- **Area growth** — the built-up share of the land within 1 km of the plot (or 1-3 km away, if the inner
  ring was already built out), 2017-2023, from a 10 m modelled land-cover map. The trend is scored: +2 points
  a year scores 100 (a rule, not calibrated). It measures building on the ground, not prices or approvals.
- **Buy / wait / walk away** — see "Decision logic" above. A strong location is BUY only after the legal checks;
  unverified title is never treated as clear and stays first on the "before you pay" list.
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

