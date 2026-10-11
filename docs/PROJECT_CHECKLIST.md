# TerraScope project checklist

The single current progress checklist. Last updated 2026-10-11 on branch `sai/terrascope-progress`.

Rules: an item is "verified" only when a recorded check exercised the real behaviour (real services, real
data, or the browser), not because code exists, a mocked test passes or a page loads. "Implemented" without
"verified with real data" means exactly that. History and causes are in [PROJECT_JOURNEY.md](PROJECT_JOURNEY.md)
(J-numbers below).

## Implemented and verified

- [x] **Local setup, start and stop**
  - Behaviour: `terrascope.cmd start | stop | status | fetch-data [region]`. Reuses healthy services, refuses ports
    held by other programs, stops only its own processes. Your reports persist in `.local-ui-check/backend.sqlite3`.
  - Evidence (2026-10-11): about a dozen stop/start cycles this session; after the audit, a normal `start` served
    all 91 of your reports, and the file was byte-identical to its pre-audit backup.
  - Remaining: the Docker Compose path is still unverified (J-05).
  - Files: `scripts/terrascope.ps1`, `terrascope.cmd`. Commits `f463ea1`, `8f9119a`.
- [x] **India-wide coverage, union territories included**
  - Behaviour: parcels in any state or UT are analysed; outside India gives `outside_india` before any
    collection.
  - Evidence (2026-10-11, API benchmark): Puducherry was analysed; Colombo was refused in 0.2-0.3 s; Patna and
    Kadapa were analysed without a regional cache.
  - Remaining: the boundary is geoBoundaries, not Survey of India (J-30).
  - Files: `data-pipeline/connectors/regions.py`.
- [x] **Search autocomplete (local index, no public geocoder while typing)**
  - Behaviour:
    - Suggestions appear 120 ms after typing stops. A newer keystroke cancels the older request.
    - Keyboard (arrows / Enter / Esc) and mouse selection both work, and Enter submits after a mouse pick.
    - Covers towns, localities, districts, states and UTs, colleges, stations, lakes, older names (Madras,
      Bombay, Cuddapah) and PIN codes. PIN results are labelled approximate.
  - Evidence (2026-10-11, browser and API):
    - Typing sends only `/api/v1/search/suggest`; a test makes any network call fail the suggest endpoint.
    - Over HTTP: p50 2.9 ms, p95 24.6 ms, max 270 ms (n=100).
    - Leh, Kavaratti, Port Blair, Silvassa, Daman, Chandigarh and Puducherry all found.
  - Remaining:
    - Explicit Search with no local match sends one rate-limited Nominatim query, which is allowed for
      single searches.
    - "VIT" alone ranks a Rajasthan village first ("vit vellore" works).
  - Files: `backend-api/routers/places.py`, `data-pipeline/fetch_data.py` (index build), `frontend/src/pages/Search.tsx`.
    J-36. Commits `6ba3e51`, `8f9119a`.
- [x] **Map and boundary drawing**
  - Behaviour:
    - No invented default box. Draw / Edit (with visible Save and Cancel) / Clear.
    - The map keeps your zoom, and the boundary survives going to the report and back.
    - Analyze stays disabled until a boundary exists.
  - Evidence (2026-10-11, browser):
    - Drew a 0.33 ha plot in Katpadi; edited it to 0.54 ha and saved; cleared; redrew.
    - Returned from the report with the boundary intact.
  - Remaining:
    - Leaflet-draw needs a mouse move before each click, which affects automation only.
    - From a reopened saved report, "Workspace" returns to search.
  - Files: `frontend/src/pages/ParcelWorkspace.tsx`, `frontend/src/main.tsx`. J-37.
- [x] **Invalid and outside-coverage polygons**
  - Behaviour: each gets a clear 400 before any collection:
    - self-intersecting;
    - zero area;
    - out-of-range coordinates;
    - over 1,000 ha (`MAX_PARCEL_AREA_HA`).
  - Outside India gets an "Outside coverage" card, and nothing is saved.
  - Evidence (2026-10-11): API probes and 5 regression tests.
  - Files: `data-pipeline/connectors/osm_infrastructure.py`, `etl_pipeline.py`, `test_etl_india.py`. J-38.
- [x] **Saved reports**
  - Behaviour: every report is listed (the cap of 50 is gone), and a report reopens in 67-89 ms in the browser
    (API p50 6 ms).
  - Evidence (2026-10-11):
    - In the audit store, 95 reports were listed and reopened after several service restarts.
    - Your 91 reports are unchanged.
  - Files: `backend-api/routers/parcels.py`, `frontend/src/lib/api.ts`. J-39.
- [x] **Flood assessment, presented per mechanism**
  - Behaviour:
    - One line per mechanism with its measurement: river scenarios, historical inundation (not integrated),
      surface water, terrain and nearby water, rainfall and coastal (not assessed).
    - Scenario table and sources are in an expandable section.
    - No flood score or safety percentage, and flood evidence feeds no score or price.
  - Evidence (2026-10-11, browser): Velachery marsh-edge parcel (2.8 ha) shows the parcel flooded from 1-in-10
    up to 4.96 m deep, and a lake 178 m away.
  - Remaining: no rainfall/pluvial, coastal or historical layer (J-32).
  - Files: `frontend/src/pages/Report.tsx`. J-31, J-43.
- [x] **Error handling for analysis and evaluation**
  - Behaviour:
    - API errors show their sentence, not raw JSON.
    - A valuation outage never costs the report.
    - Bad valuation input gets a 400 even with no data.
  - Evidence (2026-10-11): integration suite, plus API probes.
- [x] **Performance: satellite collection, evaluation, search, reopen**
  - Evidence (2026-10-11): see the measurements below.
  - Files: `data-pipeline/connectors/satellite_planetary.py`, `ml-models/rag_pipeline/reason.py`,
    `scripts/benchmark.py`. J-40, J-41.
- [x] **Tests and Git synchronisation**
  - Evidence (2026-10-11):
    - data-pipeline 62, ml-models 37, backend-api 9 and valuation 48 passed.
    - Integration 17 passed, 1 skipped (no price data), in 82 s.
    - Frontend production build passes.
    - Pushed to `origin/sai/terrascope-progress`.
  - Note: the unit tests are mocked or synthetic; the integration suite and the benchmark used real providers.

## Pending, partially implemented, failing or blocked

- [ ] **Land valuation (live prices): BLOCKED on permitted data**
  - Implemented: the import contract with provenance and reuse basis; cleaning and de-duplication; the
    comparable-property estimator; refusals; and a UI labelled "Listing-based estimated price range".
  - Verified only on synthetic test rows.
  - Every real parcel today gets "No price estimate: no licensed listing feed or permitted price data is
    loaded".
  - Blocker: no openly licensed listing or transaction dataset exists for these parcels. See
    [SETUP_VALUATION.md](SETUP_VALUATION.md) for what was checked and what is needed (a licensed feed, which is a
    paid decision; owner/broker permission; or authorised registration data).
  - Files: `valuation/`, `backend-api/routers/valuation_routes.py`. J-19, J-42.
- [ ] **Prediction validation: NOT YET VALIDATED**
  - The harness (`python -m valuation.evaluate`) reports:
    - observation counts per split, regions, land uses and dates;
    - MAE, median APE, RMSE, and the share within ±10/20/30%;
    - prediction coverage and interquartile containment;
    - grouped temporal and geographic holdouts;
    - a model-vs-baseline comparison.
  - Zero real observations exist, so no accuracy figure exists, and none is quoted anywhere.
  - Synthetic self-checks are tests only, not accuracy. J-42.
- [ ] **Legal evidence**
  - No land-records, encumbrance or approval source is integrated.
  - Legal Safety is "unavailable" for every parcel, so every Indian parcel gets INSUFFICIENT_EVIDENCE (J-17).
  - The RERA seed covers Maharashtra only and is not installed (J-14).
- [ ] **Growth evidence**
  - Not integrated. NDVI/NDBI change is shown as land cover only; no economic growth source exists (J-17).
- [ ] **Accessibility outside installed regions**
  - Works only where `fetch-data <region>` has been run (Tamil Nadu + Puducherry installed). Elsewhere the report
    says so and gives the command.
  - OSM schools are sparse.
  - Distances are straight-line, not travel distances. The max-distance preferences are accepted but not
    applied (J-23).
- [ ] **Uploads and evidence citations**
  - Upload works: TXT and PDF; text is extracted and listed in the ledger (verified in the browser 2026-10-11).
  - No document is read or cited by any analysis, because grounded retrieval needs `GROQ_API_KEY` (not set,
    J-26). The ledger now says this instead of "indexed for grounded retrieval" (J-44).
  - The valid-PDF browser check is outstanding (J-02).
- [ ] **Performance: cold analyses and parcels outside installed regions**
  - A first analysis of a new parcel still takes 11-19 s: satellite reads (~10-13 s), plus remote DEM reads for
    parcels without a regional cache (3.7 s alone, 7-18 s under contention).
  - A DEM/GSW result cache, or regional tiles, is the next step (J-41).
- [ ] **Accessibility (UI a11y)**
  - The search box is a proper combobox with listbox options, and buttons have labels.
  - No audit with a screen reader or contrast tool has been done.
- [ ] **Docker Compose path**: unverified (J-04, J-05).
- [ ] **Browser screenshot verification**
  - In the app's browser pane, screenshots intermittently time out or come back black or tiled at an emulated
    1440×900 viewport.
  - Checks used DOM/text reads plus screenshots at the pane's own width (J-45).

## Measurements (2026-10-11, same machine and network, test geometry, not surveyed boundaries)

| What | Before | After | Sample |
|---|---|---|---|
| Analysis, warm (same parcel again), median | 10.9 s (cache off) | 0.66 s | 6 parcels × 1 warm run each; after: 2 warm runs |
| Analysis, cold (new parcel), median | 13.9 s | 12.4 s | 6 parcels; satellite-bound, essentially unchanged |
| Satellite collector, warm | 9.4-14.3 s | 0.08-0.11 s | 6 parcels |
| Satellite series, cold, standalone (Kadapa) | 11.5-13.8 s (8 workers) | 10.5-12.2 s (12 workers) | n=3 each |
| First evaluation after a service start | 36.0 s | 0.56 s | 1 browser run each |
| Evaluation, warm, p50 / p95 | 0.25 / 0.35 s | 0.24 / 0.25 s | n=12 / 18 |
| Search suggestion (HTTP), p50 / p95 | each typing pause sent a public Nominatim request (not timed) | 2.9 / 24.6 ms | n=100 |
| Saved-report reopen, API p50 | 9 ms | 6 ms | n=12 / 18 |
| Valuation request | 2-5 ms (refusal) | 2-3 ms (refusal); 13.5 ms p50 compute on ~5,000 synthetic rows | n=12-50 |
| Errors / timeouts | 0 | 0 | benchmark runs |

Output equivalence: the satellite series and flood evidence fingerprints were identical with and without
the cache for every parcel and run. Caching cuts network time; it does not change any algorithm's complexity.
