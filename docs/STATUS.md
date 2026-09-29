# TerraScope local development status

Last updated: 2026-09-29 · branch `sai/terrascope-progress` (from `origin/main`) · pushed to https://github.com/riit3sh/TerraScope

This work was developed in a local folder unpacked from a ZIP, whose Git history is unrelated to the
team repository. It was transferred onto a fresh branch cut from `origin/main` rather than merged, and
no teammate's file was deleted in the process.

## Run it

```bash
bash scripts/run_local.sh      # backend :8000, data-pipeline :8001, ml-models :8002, UI :5173
bash scripts/stop_local.sh
```

Open http://localhost:5173. Docker is not required for this path. The PostGIS snapshot archive is skipped, and the backend still stores every snapshot in `.local-ui-check/backend.sqlite3`.

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
