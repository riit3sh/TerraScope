# TerraScope local development status

Last updated: 2026-10-06 · branch `sai/terrascope-progress` (pushed to origin).

## Run it

```bat
terrascope.cmd setup     :: first run only: .venv + requirements + npm ci
terrascope.cmd start     :: backend :8000, data-pipeline :8001, ml-models :8002, UI :5173
terrascope.cmd stop
```

The old `scripts/run_local.sh` force-killed whatever held those ports and seeded a demo report on every start. It has been replaced (see README → Native Windows).

Open http://localhost:5173. Docker is not required for this path. The PostGIS snapshot archive is skipped, and the backend still stores every snapshot in `.local-ui-check/backend.sqlite3`.

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
