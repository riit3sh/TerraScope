# TerraScope local development status

Last updated: 2026-10-06 · branch `sai/terrascope-progress` (pushed to origin).

## Run it

```bat
terrascope.cmd setup                  :: first run only: .venv + requirements + npm ci
terrascope.cmd fetch-data             :: first run only: India boundary (~46 MB)
terrascope.cmd fetch-data tamil-nadu  :: optional regional cache (any state/UT; --list)
terrascope.cmd start                  :: backend :8000, data-pipeline :8001, ml-models :8002, UI :5173
terrascope.cmd stop
```

The old `scripts/run_local.sh` force-killed whatever held those ports and seeded a demo report on every start. It has been replaced (see README → Native Windows).

Open http://localhost:5173. Docker is not required for this path. The PostGIS snapshot archive is skipped, and the backend still stores every snapshot in `.local-ui-check/backend.sqlite3`.

## India-wide coverage and river flood hazard (2026-10-06)

**Scope correction.** TerraScope covers all of India. The Tamil Nadu work from the previous milestone is now the first regional cache, `tamil-nadu`, which also covers Puducherry. It is no longer a restriction.

**Coverage.**
- **Boundary:** geoBoundaries gbOpen IND ADM1 (DataMeet India / Election Commission of India, CC BY 2.5 IN, 36 states and UTs). The source data was updated 2023-04-05 and the build is dated 2023-12-12. It is not a Survey of India boundary; coastlines and borders are generalised.
- **Acceptance:** a parcel is accepted when at most 1% of its area falls outside the India outline. Otherwise it gets `outside_india` before any collector runs, and nothing is saved.
- **State attribution:** a parcel crossing a state border lists every state, with its share.
- **Search:** India-wide, union territories included.
- **Missing data:** a missing regional cache is reported per layer, with the install command (for example `terrascope.cmd fetch-data andhra-pradesh`), and never blocks the other collectors.

**Regional data.** `fetch-data <slug>` works for all 36 states and UTs. It picks the Geofabrik India zone by its `.poly` coverage, checks disk space, reuses any extract and tiles already on disk, and builds `data-cache/regions/<slug>/osm.sqlite`. Nothing India-wide is downloaded automatically. The old `tn-data/` was moved, not deleted, into `data-cache/`; the previous store is kept under `regions/tamil-nadu/previous-build-2026-10-06/`. The rebuilt `tamil-nadu` cache took 9 minutes from the PBF already on disk and needed 2 new DEM tiles (28 MB, for Mahe and Yanam). Known limit: Geofabrik's northern zone covers 41% of Ladakh and 79% of Jammu & Kashmir as drawn in the boundary file.

**Flood evidence (no score).**
- **JRC river flood hazard maps v2.1.2** (2026-01-12, CC BY 4.0, ~90 m, return periods 1-in-10 to 1-in-500 years). Read remotely by HTTP range requests, with no account; results are cached per parcel. Cell semantics were checked against the tiles:
  - -9999 means "no modelled inundation", and also covers open sea, so it is never read as "safe".
  - Permanent-water cells are excluded from exposure.
  - Spurious-depth cells are flagged, and their depths withheld.
  - Areas no tile covers are "not modelled".
  - A failed read is "unavailable" and is not cached.
  - Each scenario also reports the share of land within 500 m modelled as flooded.
- **NRSC Flood Affected Area Atlas (1998-2022): not integrated.** The technical document says the spatial maps are "hosted on NDEM geoportal". NDEM offers viewing, and no machine-readable download was found (the old `hydrologicaldisasters` page returns 404). The original `ndrf.nrsc.gov.in` host does not resolve; the document is reachable at `ndem.nrsc.gov.in/documents/downloads/allindia_flood_techdoc.pdf`.
- **Kept and labelled:** surface water seen 1984-2021 (not flood history), terrain relative to mapped water (not HAND), and rainfall/waterlogging and coastal flooding, both marked not assessed.
- **Report:** shows "Partial flood assessment available" with a scenario table and the six mechanisms. The 0-100 terrain figure is no longer shown; the elevation row gives metres. Flood Safety stays unscored (status `partial`), and the "start at 100" rule is not enabled.

**Test parcels** (about 100 m squares, via the API, 2026-10-06; scores use the investor lens).

| Parcel (SW corner, size) | Why chosen | Analysis | Accessibility | River flooding (parcel / land within 500 m flooded, at 1-in-100) | Other flood evidence |
|---|---|---|---|---|---|
| VIT Vellore (79.1550 E, 12.9688 N; 0.0009°) | named in the request; VIT campus | 19.3 s | 86.5: road 108 m, hospital 75 m, school 568 m | none in any scenario / 0% (2.5% at 1-in-200) | +12.3 m above VIT Lake (378 m) |
| Chennai, Velachery (80.2120 E, 12.9856 N; 0.0008°) | beside Velachery Lake | 15.6 s | 92.2 | from 1-in-20 (19%); 100% at 1-in-100, max 2.49 m / 77% | lake 162 m, +3.6 m; GSW buffer up to 77% occurrence |
| Kadapa (78.8441 E, 14.4507 N; 0.0009°) | the team's existing Kadapa pilot point | 18.2 s | unavailable: no regional cache (install command shown) | none / 0% | elevation 136 m (DEM read remotely) |
| Patna (85.1440 E, 25.6210 N; 0.0009°) | first land square south of the Ganga by GSW and the permanent-water mask | 18.4 s | unavailable: no regional cache | parcel cell dry in all scenarios / 35% of land within 500 m flooded from 1-in-10 | GSW buffer 39% ever wet |
| Puducherry, White Town (79.8330 E, 11.9340 N; 0.0009°) | union territory, now accepted | 12.2 s | 96.3 | 53% only at 1-in-500 / 17% at 1-in-100 | +1.9 m above a drain 93 m away |
| Colombo (79.8612 E, 6.9271 N) | outside India | 2.3 s | not collected | not collected | `outside_india` |

Every Indian parcel gives verdict INSUFFICIENT_EVIDENCE: Legal Safety has no land-records source, Growth is not integrated, and Flood is partial and unscored.

In the browser (headless Edge):
- searched "Puducherry railway station", drew a box about 450 × 370 m and analysed it in 18.5 s
- the flood panel showed 7 scenario rows (from 1-in-20: 59% of the parcel; 1-in-100: 86%, max 3.96 m)
- reopened the saved report with the same panel
- a box drawn across the Nepal border from Raxaul gave "Only 72.9% of the parcel lies inside India", with no report
- no page errors or failed requests

**Tests.**
- data-pipeline: 50 passed. New: India coverage and state borders, region selection, no-regional-data analysis, river-flood no-data / zero depth / permanent water / flags / unmodelled / partial / provider failure / cache reuse.
- ml-models: 37 passed. backend-api: 4 passed, on an isolated store.
- valuation: unchanged (15 passed, 5 failed for want of a trained model).
- frontend build: passes.
- integration: 17 passed, 3 skipped (price arithmetic, no model) in 6 min. An earlier run had one transient 120 s read timeout on the first document upload (hypothesis: the first download of the embedding model) and passed on rerun.

The integration suite now starts its own backend with a temporary database. The user's saved-report count was unchanged by the run (90 before, 90 after).

**Problems found and fixed during this milestone.**
- The new `partial` factor status was missing from the shared schema. The live evaluate call returned HTTP 502 until the enum was extended; a regression test was added.
- Giving `$Region` a `[Parameter()]` attribute made PowerShell stop binding `$Command` by position, so `stop` and `fetch-data` silently ran `start`. Both positions are now explicit.
- The integration-test teardown killed only the venv launcher on Windows, so the uvicorn child could keep the temporary database open. It now kills the process tree.

**Still limited.**
- Valuation has no price model.
- `location.district` is null.
- OSM school coverage is sparse.
- No rainfall/pluvial or coastal-surge dataset is integrated.
- No historical inundation layer is integrated (NRSC, see above).
- GSW buffers on the coast include the sea.
- The DEM is a surface model, so buildings and trees raise elevations.
- The integration suite takes about 25 minutes, because each test runs real analyses.

## Tamil Nadu milestone (2026-10-06, superseded by the India-wide section above)

**Coverage.** Analysis runs only for parcels entirely inside Tamil Nadu. The boundary is OSM relation 96905 minus relation 107001 (Puducherry), from the same Geofabrik extract (ODbL, data to 2026-10-04). Its area is 130,071 km², against the official 130,058 km². Puducherry town and Karaikal fall outside. Parcels outside or crossing the edge get `{"status": "outside_coverage"}` before any collector runs. Nothing is saved, and the UI shows an "Outside coverage" card instead of a report. Search suggestions are bounded to Tamil Nadu and filtered on `state == "Tamil Nadu"`, so "Pondicherry" and "Bengaluru" return nothing.

**Local data** (`terrascope.cmd fetch-data`, stored in `tn-data/`, git-ignored). Downloading took about 1 hour at ~0.7 MB/s; the OSM build took 7 minutes.

| Dataset | Version, dates and licence | Size |
|---|---|---|
| Geofabrik southern-zone PBF | data to 2026-10-04T20:20Z, ODbL 1.0 | 558 MB |
| `tn_osm.sqlite` | roads 914,607; waterways 18,543; water bodies 16,758; hospitals 6,073; bus 4,624; schools 3,166; rail stations 704 | 289 MB |
| JRC GSW v1.4 occurrence + extent | Landsat 1984-03 to 2021-12, 30 m, Copernicus "Source: EC JRC/Google" | 189 MB (8 tiles) |
| Copernicus GLO-30 | 2021 release of 2011-2015 TanDEM-X data; a 30 m surface model; Copernicus DEM licence | 1,003 MB (30 tiles) |

Planetary Computer serves both rasters. Its JRC GSW copy ends in 2020, so the newer v1.4 tiles come from JRC's own bucket.

**Accessibility** now comes from the local store; Overpass is used only with `OSM_OVERPASS_FALLBACK=true`. Each distance is measured from the parcel centroid to the nearest point on the feature's full geometry, using an R*Tree index and shapely. Midpoints are never used. Each evidence row carries the extract's data date. Accessibility scoring is unchanged.

**Flood indicators** are evidence only, and Flood Safety stays unscored:
- JRC surface-water occurrence and maximum extent, inside the parcel and within 500 m
- GLO-30 parcel elevation, and its elevation relative to the nearest mapped water within 2 km. This is a terrain indicator: not HAND and not a flood probability.
- distance to the nearest river/canal and the nearest tank/lake

The terrain-position indicator now samples the local DEM instead of Open-Elevation.

**Test parcels** (API, one run each; scores use the investor lens):

| Parcel | Analysis | Accessibility | Flood indicators | Verdict |
|---|---|---|---|---|
| Vellore city (79.132, 12.920) | 19.7 s | 86.7 (indicative): trunk road 38 m, school 629 m, hospital 395 m, bus stop 78 m, Vellore Town station 864 m | dry in GSW; within 500 m max occurrence 59%, 1.9% of pixels ever wet; +8.7 m above the Fort moat (155 m); river 1.6 km; basin 387 m | INSUFFICIENT_EVIDENCE (20% of weighting evidenced) |
| Rural Vellore, Unai (78.960, 12.890) | 11.4 s | 33.7: residential road 1.3 km, no school or rail station within 5 km, hospital 4.9 km, bus stop 2.0 km | dry in GSW to 500 m; hillside at 516 m (range 496-532); no water within 2 km; river 3.3 km; pond 2.7 km | INSUFFICIENT_EVIDENCE |
| Chennai, south of Velachery Lake (80.212, 12.986) | 15.1 s | 92.2: road 15 m, school 375 m, hospital 638 m, bus 632 m, Puzhudivakkam station 1.2 km | parcel dry; within 500 m max occurrence 77%, 13.8% of pixels ever wet; 8.8 m elevation, +3.8 m above Velachery Lake (167 m); canal 583 m | INSUFFICIENT_EVIDENCE |
| Puducherry town (79.830, 11.934) | 2.3 s | not collected | not collected | outside_coverage |
| Bengaluru (77.595, 12.972) | 2.4 s | not collected | not collected | outside_coverage |

Legal Safety is unavailable for every parcel (no land-records source) and Growth is not integrated, so no BUY/WAIT/AVOID is given. In the browser (headless Edge), the same flow passed, including the outside-coverage card for a parcel drawn from Kottakkuppam across the Puducherry border:
- search restriction
- analysis in 16 s
- the Flood indicators tab
- reopening a saved report

### Proposed Flood Safety rule (for approval; NOT enabled)

Score 0-100, higher is safer, status `indicative`. Start at 100 and apply the following, flooring at 0. "Ever wet" means the share of pixels on which GSW saw water at least once.

1. **Water inside the parcel** (GSW), as a cap:
   - max occurrence ≥ 50%: cap 10. The parcel is likely a tank bed or channel.
   - 10-49%: cap 35.
   - 1-9%: cap 60.
2. **Water within 500 m**:
   - ever wet on > 20% of pixels: −15
   - 5-20%: −8
3. **Elevation above the nearest mapped water within 2 km**:
   - < 1 m: −30
   - 1-3 m: −20
   - 3-6 m: −10
   - none within 2 km: no change, flagged "no nearby mapped water"
4. **Nearest tank/lake (eri)**: < 100 m −15; 100-300 m −8.
5. **Nearest river/canal**: < 200 m −15; 200-500 m −8.
6. **Guards:**
   - Never the sole basis for AVOID.
   - Shown as indicative.
   - Withheld when GSW and the DEM are both missing.
   - Each deduction listed in the factor basis.

Applied to the parcels above, the rule would give:
- Vellore city: 100, as no rule fires.
- Unai: 100, from no evidence of water (weak).
- Chennai/Velachery: 74. That is −8 because 13.8% of pixels within 500 m were ever wet, −10 for +3.8 m above the lake, and −8 for the lake at 168 m; the canal at 583 m gives no deduction.

The team should calibrate these thresholds against known flood events, such as the Chennai 2015 and 2023 inundation extents, before enabling the rule.

### Still failing or limited
- **Valuation:** 5 of 20 unit tests fail because no trained model file exists (unchanged).
- **District:** `location.district` is null for all parcels (Nominatim address lookup returns no district field). This predates the milestone.
- **OSM completeness:** only 3,166 schools are mapped for all of Tamil Nadu. "None within 5 km" is absence in OSM, not proof of absence.
- **Tank/lake class:** `water=basin` (often a stormwater basin) is counted as a tank/lake, and the Vellore Fort moat counts as a water feature.
- **DEM:** GLO-30 is a surface model, so urban rooftops and trees raise parcel elevation.
- **Integration tests:** moved from Pune to Tamil Nadu parcels. Their verdict assertion now accepts `INSUFFICIENT_EVIDENCE`, which has been the contract since 067d541; those tests were already stale before this milestone.
- **Old reports:** a saved report for Kadapa (Andhra Pradesh), created before the restriction, still opens.

## Native Windows setup check (2026-10-06)

Setup: `.venv` (Python 3.11.5) with all three services' requirements, including CPU PyTorch and chromadb. Frontend dependencies come from `npm ci` against the lockfile. `.env` was recreated from the template with no credentials: `DATABASE_URL`, `GROQ_API_KEY` and the NASA fields are blank, and `SATELLITE_DEMO_FALLBACK=false`.

Verified in a real browser (headless Edge via Playwright): search "Vellore" → pick suggestion → workspace → draw boundary → Analyze This Parcel (26 s) → open report → back → reopen a saved report. No backend request failed. The report correctly showed:
- Sentinel-2 satellite evidence (Planetary Computer, no credentials needed)
- Accessibility 76.94, marked "indicative only"
- Legal, flood and growth marked "not assessed"
- Verdict `INSUFFICIENT_EVIDENCE`
- Valuation "unavailable"

All three saved reports reopen. Health: `:8000/api/v1/health`, `:8001/health`, `:8002/health` return their service names, `:5173` returns 200, and CORS allows `http://localhost:5173`.

Launcher checks:
- Restart reuses healthy services.
- `stop` leaves no processes behind.
- An unrelated process on 5173 or 8002 is refused with its pid and left running, and nothing is started.
- Services survive closing the console that launched them.

Tests: backend-api 2 passed, data-pipeline 6 passed, ml-models 6 passed. Valuation: 15 passed and 5 failed, all because no model is loaded. `valuation/artifacts/*.joblib` is git-ignored and must be regenerated with `python -m valuation.train`.

### Unresolved: OpenStreetMap infrastructure often misses the 35 s deadline

A focused check through the connector's own `_request_overpass` (Vellore, 1.5 km roads and 3 km schools, `out geom`) failed after 35.4 s:
- `overpass-api.de` returned **HTTP 504** to the GET request.
- `overpass.private.coffee` and `overpass.kumi.systems` each hit the 25 s read timeout.

With a 5 s hedge delay the third mirror starts at about 10 s, so it can only finish around 35 s. The retry budget therefore does not fit inside `EVIDENCE_COLLECTION_DEADLINE_SECONDS=35`.

It is not established that the 504s are purely upstream. A tiny query, and the same query sent as POST, have each succeeded at other moments, and one browser analysis did return road and school evidence. Next steps:
1. Compare GET with POST for the same query, rate-limited.
2. Size the hedge and timeouts so that every mirror gets a real attempt within the deadline.

Keep `out geom`. Nearest-road distance must be measured to the road geometry, not to its midpoint.

Also: `GROQ_API_KEY` is not set, so explanations and citations use the deterministic summary. There is no RERA seed CSV and no price model.

## Completed

| Commit | Change |
|---|---|
| `4f93cb7` | WIP checkpoint of the existing source. `.gitignore` now also excludes `.local-ui-check/`, API caches, `*.joblib` model binaries and the `tsc -b` emits of `vite.config.ts`. |
| `a13a70b` | **Fixed `[Errno 11001] getaddrinfo failed` on analysis.** The failing hostname was `data-pipeline` (and next, `ml-models`): the backend defaulted to Compose DNS names that resolve only inside Docker. The defaults are now `127.0.0.1:8001/8002`, and Compose still sets its own values. Connection errors now name the service and address. |
| `2b8a579` | Valuation refuses to quote prices when the only model was trained on synthetic rows (`reason: synthetic_model_only`). Demo figures need `VALUATION_ALLOW_SYNTHETIC=true` and are then labelled DEMO DATA. |
| `bab54ca` | The verdict text says "land records not provided, so legal safety is unverified" when that is the case. Scores are unchanged. |
| `bc3b551` | RAG import errors now report the real cause (`No module named 'chromadb'`) instead of `No module named 'retrieve'`. |
| `e669ca8` | Every evidence row in the seeded UI demo report is labelled FIXTURE. It previously claimed live Overpass/Open-Elevation data, NASA AppEEARS imagery and an invented RERA number. |

## Verified flow (live services, API level)

Geocode "Vellore" → analyze drawn polygon (200, ~4 s) → upload TXT evidence (indexed) → evaluate (verdict WAIT, composite 70.0) → valuation (explicit `unavailable / synthetic_model_only`) → saved-reports list → reopen with document and evaluation. Requests carried the UI's `Origin`, and CORS allows `http://localhost:5173`.

The flow was **not** clicked through in a real browser this session. The checks were the frontend type-check, a production build and the dev server serving on :5173.

## Test results (2026-09-28)

| Suite | Result |
|---|---|
| `backend-api/tests` (new) | 2 passed |
| `data-pipeline` | 9 passed |
| `ml-models` | 19 passed |
| `valuation` | 20 passed |
| `tests/integration` (against the native local stack) | 18 passed, 2 skipped (price-arithmetic tests skip because no price is produced) |
| Frontend `tsc -b` / `vite build` | pass (bundle-size warning only) |

## Remaining issues and blockers

1. **No real land-price data.** The only model is trained on `valuation/fixtures/synthetic_land_prices.csv`, so every valuation is refused. It needs a real price CSV, then `python -m valuation.train <csv>`.
2. **No real Groq key.** `.env` has the placeholder `demo-groq-api-key`. Locally, `chromadb`, `sentence-transformers` and `torch` are also not installed (they are in the Docker image). As a result, grounded AI explanations and citations of uploaded documents do not run. The deterministic score summary is used instead.
3. **No NASA AppEEARS credentials.** The satellite series is SYNTHETIC. It is labelled that way in the evidence, and change detection on it is not meaningful.
4. **RERA seed missing.** `data-pipeline/data/raw/maharera_seed.csv` does not exist, so RERA status is always "unknown". The seed would cover Maharashtra only, not Tamil Nadu.
5. **Legal scoring decision (owner's call).** Missing land records add only 10 risk points, so an unrecorded parcel shows legal safety 90. The reasoning now flags this, but the weighting is unchanged.
6. **Docker/Compose path not verified this session.** Docker Desktop was not running. `.env` `DATABASE_URL` uses the Compose-only host `postgres`, and `run_local.sh` blanks it for local runs.
7. `.local-ui-check/backend.sqlite3` holds about 38 earlier reports, which may include demo seeds from before `e669ca8` with the old labels. They were left untouched.
8. `frontend/package.json` pins every dependency to `latest`, so builds are not reproducible.
9. Pushing waits on repository access.
