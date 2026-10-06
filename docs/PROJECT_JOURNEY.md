# TerraScope project journey

This is TerraScope's running log of problems and how each was resolved. It records what went wrong, what we
confirmed, what we changed, how we checked it, and what is still open. Failed attempts stay in the log, with
the reason the approach changed.

## How to maintain this log

- Add or update an entry whenever a problem is found, an approach changes, or a milestone lands. Commit the
  log together with that milestone.
- Each entry records: the date and the problem as a user saw it; the root cause, confirmed or labelled
  **hypothesis**; the changes and files; the verification and its result; remaining limitations; related
  commits; and a status.
- Status values:
  - **unresolved**: no working fix yet.
  - **in progress**: work is underway, or a change has landed but its verification is incomplete.
  - **fixed and verified**: a recorded check shows the user-visible problem is gone.
  - **superseded**: replaced by a different approach. The entry says which one.
- A commit message alone is not verification. Say who checked what, when, and how. If a result comes only from
  a commit message or a session summary, say so.
- Never put credentials, personal documents or downloaded datasets in Git or in this file.

## Sources used for the backfill (2026-10-06)

- Git history of `origin/main` (27 commits by riit3sh, 2026-09-08 to 2026-09-09) and `sai/terrascope-progress`.
- A second local clone, used from 2026-09-28 to 2026-09-29 on branches `dev` and `feature/local-completion`.
  Its commits were never pushed, and hashes marked *local-only* do not resolve on GitHub. Its root commit
  `4f93cb7` checkpointed about 57 files of uncommitted work done between 2026-09-22 and 2026-09-28. That work
  was published on 2026-09-29 as `1fd913f..8e52ada`. This was checked by comparing file blobs: every file
  touched by the local-only commits `a13a70b`, `2b8a579`, `bab54ca`, `bc3b551` and `e669ca8` appears
  byte-identical in a published commit, and the tree of local `9ad51cb` equals published `4a01704` (apart from
  two tracked `vite.config` emits).
- Claude Code session transcripts:
  - 2026-09-22 to 09-29: main development, including the 09-29 audit
  - 2026-09-28: local completion
  - 2026-10-06: setup recovery, followed by the Tamil Nadu milestone (in progress)
- `docs/STATUS.md`, `README.md`, `DEMO_SETUP.md`, `docs/SETUP_VALUATION.md`.

## Timeline

| Date | Milestone |
|---|---|
| 2026-09-08 – 09 | Team scaffold and Review 2 fixes on `main`: NASA AppEEARS satellite, place search, Groq explanations |
| 2026-09-22 – 27 | Local development on a ZIP copy: upload fixes, valuation module, parallel evidence collection. Docker unusable |
| 2026-09-28 | Local Git checkpoint. getaddrinfo fixed in code. Synthetic prices refused (local-only commits) |
| 2026-09-29 | Collaborator access granted. Work pushed to `sai/terrascope-progress`, draft PR [riit3sh/TerraScope#1](https://github.com/riit3sh/TerraScope/pull/1). Evidence audit. Accessibility geometry. Real Sentinel-2 |
| 2026-10-06 | Setup recovered on a fresh clone. Safe Windows launcher. Tamil Nadu coverage and local data (`80eadd5`), then the scope corrected to all of India, with JRC river flood hazard |

## Status summary

| ID | Issue | Status |
|---|---|---|
| J-01 | Review 2 UI flow defects (search, CORS, draw crash, report navigation) | fixed and verified |
| J-02 | Uploads went to parcel `'pending'`; PDFs never indexed | in progress |
| J-03 | Retrieval cache ignored newly uploaded documents | fixed and verified |
| J-04 | Disk full and Docker unusable during development | unresolved |
| J-05 | Docker Compose path never verified | unresolved |
| J-06 | Analysis failed with `[Errno 11001] getaddrinfo failed` | fixed and verified |
| J-07 | data-pipeline needed PostGIS; local persistence | fixed and verified |
| J-08 | Undefined `_downstream_error` (regression from J-06) | fixed and verified |
| J-09 | Unsafe local launchers | fixed and verified |
| J-10 | Setup recovery on a fresh clone | fixed and verified |
| J-11 | Seeded demo report claimed live evidence | fixed and verified |
| J-12 | UI simulated progress and placed markers at invented positions | in progress |
| J-13 | RERA district match reported as registration | fixed and verified |
| J-14 | No usable RERA data for the parcels we test | unresolved |
| J-15 | Flood Safety 50 for every parcel; terrain proxy | superseded by J-17 |
| J-16 | Legal Safety 90 from missing land records (warning text) | superseded by J-17 |
| J-17 | Scores and verdicts not supported by evidence | fixed and verified |
| J-18 | Synthetic valuation shown as prices for real parcels | fixed and verified |
| J-19 | No real land-price data | unresolved |
| J-20 | NASA AppEEARS satellite integration | superseded by J-22 |
| J-21 | Invented satellite series as fallback | superseded by J-22 |
| J-22 | Real Sentinel-2 observations via Planetary Computer | fixed and verified |
| J-23 | Accessibility measured to road midpoints; preferences ignored | fixed and verified |
| J-24 | Overpass slowness and timeouts | superseded by J-28 / J-30 (local OSM; Overpass opt-in) |
| J-25 | RAG import error hid its real cause | fixed and verified |
| J-26 | Groq explanations never run with a real key | unresolved |
| J-27 | Repository access and publication | fixed and verified |
| J-28 | Tamil Nadu coverage and local-data milestone | superseded by J-30 |
| J-29 | Minor open items | unresolved |
| J-30 | Scope correction: India-wide coverage, regional caches | fixed and verified |
| J-31 | Flood assessment from river flood hazard maps | fixed and verified (evidence only; no score by design) |
| J-32 | NRSC historical flood footprints not machine-readable | unresolved (access blocker) |
| J-33 | Launcher bound `stop` to `$Region` and ran `start` | fixed and verified |
| J-34 | `partial` factor status rejected by the shared schema | fixed and verified |
| J-35 | Integration tests wrote fixtures into the user's saved reports | fixed and verified |

---

## J-01 Review 2 UI flow defects

- **Date / problem:** 2026-09-08 to 09-09. Address search would not load results. The frontend origin was
  refused by the backend (CORS). Opening the Leaflet draw workspace crashed. The report button could be used
  before the analysis payload existed, and analysis completion was tied to navigation.
- **Root cause:** not recorded. Only the commit messages exist.
- **Changes:** `backend-api/routers/parcels.py`, `backend-api/src/terrascope_backend_api/main.py`,
  `frontend/src/pages/{Search,ParcelWorkspace,Report}.tsx`, `frontend/src/lib/api.ts`. Also added cached,
  India-restricted place suggestions.
- **Verification:** no record at the time. Verified indirectly on 2026-10-06 by a browser run (headless Edge
  driven by Playwright): search "Vellore" → pick a suggestion → workspace → draw a boundary → analyse → open
  the report → back → reopen a saved report. Every step worked, and no backend request failed. The script
  first stalled at selecting a suggestion and at the draw control. Both stalls were traced to the script, not
  the app. For the draw control, the stock Leaflet toolbar is hidden (`.leaflet-draw{display:none}`), and the
  app's own **Draw** button triggers it.
- **Remaining limitations:** none known.
- **Commits:** `897e4be`, `77bbb32`, `18e92df`, `02e033f`, `f4c07d1`, `1629236`, `5097d3b`, `0651d16`.
- **Status:** fixed and verified.

## J-02 Uploads went to parcel `'pending'`; PDFs were never indexed

- **Date / problem:** found 2026-09-22 by reading the code. Documents uploaded in the workspace never reached
  the analysed parcel. The Uploaded Documents tab stayed empty and retrieval never saw them. PDFs were accepted
  but never text-extracted, so `text_indexed` was always false. No `user_upload` evidence row was ever
  produced.
- **Root cause (confirmed):** `ParcelWorkspace.tsx` called `uploadEvidence('pending', file)` before a parcel
  existed. This is present in Git from the scaffold `de529c2` through `origin/main` `2681f14`. The upload route
  set `text_content=None` for every non-TXT file.
- **Changes:**
  - The workspace queues the `File` objects, creates the parcel, uploads against the real `parcel_id`, then
    evaluates (`frontend/src/pages/ParcelWorkspace.tsx`).
  - `pypdf` extracts the text. A scanned or malformed PDF is stored with `text_indexed: false`, and the UI says
    "stored · no text extracted" (`_document_text` in `backend-api/routers/parcels.py`).
  - `_with_document_evidence` adds one ledger row per document (`ml-models/pipeline.py`).
  - An uploaded document never unlocks a legal score (`ml-models/scoring_engine/test_evidence_gates.py`).
- **Verification:**
  - 2026-09-22: static checks only (build, direct asserts). A full disk blocked any runtime check (J-04).
  - 2026-09-28: a TXT upload was indexed (API level). The integration suite against the native stack gave 18
    passed and 2 skipped. It covers: a malformed PDF is stored with `text_indexed=false`, an `.exe` is
    rejected with 400, and a document uploaded after an evaluation appears in the next evaluation.
- **Remaining limitations:**
  - Extraction from a valid text PDF has not been checked end to end.
  - Scanned PDFs are not OCR'd.
  - LLM citation of uploaded text needs a Groq key (J-26).
  - No browser run has uploaded a file: the 2026-10-06 run did not.
  - Document extraction is not title verification.
- **Commits:** local-only `4f93cb7`. Published in `ef01630` (backend), `681c2ea` (frontend), `09078fe`
  (pipeline) and `4aeaf44` (integration tests, `malformed.pdf`).
- **Status:** in progress. The code has landed, but valid-PDF and browser upload checks are outstanding.

## J-03 Retrieval cache ignored newly uploaded documents

- **Date / problem:** 2026-09-25 brief. Re-evaluating after an upload returned an answer that had never seen
  the new document.
- **Root cause (confirmed):** the cache key was (snapshot id, question), and an upload changes neither.
- **Changes:** the key now includes a digest of the document set. Optional AI budgets are bounded so a slow
  Groq call degrades instead of stalling the report, and the Chroma store path is configurable. Files:
  `ml-models/pipeline.py`, `ml-models/rag_pipeline/*`, `ml-models/test_retrieval_cache.py`.
- **Verification:** unit tests pass (35 ml-models tests on a clean export of `f463ea1`, 2026-10-06). The
  integration test `test_upload_after_an_evaluation_reaches_the_next_evaluation` passed on 2026-09-28.
- **Remaining limitations:** see J-26 for whether retrieval reaches a real LLM.
- **Commits:** `09078fe`.
- **Status:** fixed and verified.

## J-04 Disk full and Docker unusable during development

- **Date / problem:**
  - 2026-09-22: the stack could not be run end to end because the disk was full. The session reported Docker's
    image store as corrupted and needing a full rebuild (`docker system prune -a --volumes`). The owner chose
    to manage disk space personally, and no prune was run.
  - 2026-09-26: the Docker daemon was still down after a stale-socket crash, left alone at the owner's request.
  - Separately, `docker compose build` had died on a pip read timeout while pulling PyTorch.
- **Root cause:** disk space was confirmed at the time. Store corruption is **hypothesis**: it was reported by
  the session and not diagnosed further.
- **Changes:**
  - pip `--retries 10 --timeout 180` for the image build.
  - CPU-only PyTorch for the ML image (`ae85ab2`, 2026-09-09).
  - `.dockerignore` files: `COPY . .` had been copying the Windows host's `node_modules` over the container's
    Linux copy (`1fd913f`).
  - Development moved to a native Windows run (J-06, J-07, J-09).
- **Verification:** none for Docker.
- **Remaining limitations:** free space on C: was 25 GB on the morning of 2026-10-06 and 21 GB (96% used) at
  about 15:50 IST. Check headroom before large downloads (J-28). Nothing was deleted to make room.
- **Commits:** `ae85ab2`, `1fd913f`.
- **Status:** unresolved. Docker has not been brought back in any recorded session.

## J-05 Docker Compose path never verified

- **Date / problem:** open since 2026-09-22. No recorded session has run the stack under Compose
  successfully.
- **Root cause:** not applicable; untested. Docker was down (J-04), and from 2026-09-26 the work used the
  native path.
- **Changes made for Compose without running it:**
  - Volumes for the backend SQLite store, the vector index and the satellite cache, which previously lived in
    `/tmp` or an image layer (`ef01630`).
  - The evaluate timeout was raised above the ML service's own AI budget.
  - The Dockerfile copies `data-pipeline/data`.
- **Verification:** none. `4aeaf44` states that the integration tests were not run against Compose.
- **Remaining limitations (inferred from code, not run):**
  - `docker-compose.yml` defaults `SATELLITE_PROVIDER=appeears` and `SATELLITE_DEMO_FALLBACK=true`. Without
    Earthdata credentials, a Compose run would take the AppEEARS path and serve the labelled SYNTHETIC
    series, not real Sentinel-2 (see J-21, J-22).
  - `DATABASE_URL` defaults to the Compose host `postgres`.
- **Commits:** `ef01630`, `1fd913f`.
- **Status:** unresolved.

## J-06 Analysis failed with `[Errno 11001] getaddrinfo failed`

- **Date / problem:** reported by the owner on 2026-09-26. "Analyze This Parcel" returned "Initial evidence
  collection failed: [Errno 11001] getaddrinfo failed".
- **Root cause (confirmed 2026-09-26, reconfirmed 2026-09-28 by resolving each hostname):**
  - The backend fell back to `http://data-pipeline:8001` and `http://ml-models:8002`. These are Compose DNS
    names, but nothing was running in Docker.
  - Two further blockers surfaced in turn: data-pipeline was not running at all (J-07), and
    `NOMINATIM_USER_AGENT` was not loaded from `.env` outside Compose.
  - External providers all resolved; this was never an external DNS problem.
- **Attempt 1 (2026-09-26), superseded:** fixed only in the launcher. `scripts/run_local.sh` set
  `DATA_PIPELINE_URL`/`ML_MODELS_URL` to `127.0.0.1`, started data-pipeline and loaded `.env`. The session had
  written that launcher earlier and had omitted `DATA_PIPELINE_URL`.
  - Verified: a browser analysis at Vellore returned HTTP 200 in about 8 s.
  - Why the approach changed: a backend started any other way still defaulted to Compose names. This was
    reproduced on 2026-09-28.
- **Attempt 2 (2026-09-28):**
  - Code defaults are now `127.0.0.1:8001/8002`, and Compose still sets its own values.
  - A connection error names the service and its address.
  - Files: `backend-api/routers/parcels.py`, `backend-api/tests/test_service_urls.py`, `.env.example`.
- **Verification:**
  - 2026-09-28: the two new tests failed before the fix and passed after it. A live analysis with no URL
    overrides returned 200 in about 4 s (API level).
  - 2026-10-06: the full browser flow through the new launcher passed (J-10).
- **Remaining limitations:** this change introduced J-08.
- **Commits:** local-only `a13a70b`, published in `ef01630`. `4aeaf44` describes the launcher attempt.
- **Status:** fixed and verified.

## J-07 data-pipeline needed PostGIS; local persistence

- **Date / problem:** 2026-09-26. data-pipeline would not start on Windows because `db/models.py` uses a
  PostGIS `Geometry` column and there was no Postgres.
- **Root cause (confirmed):** a hard dependency on the PostGIS snapshot archive.
- **Changes:**
  - The archive turns itself off when `DATABASE_URL` is unset. A URL that is set but unreachable still fails
    loudly (`data-pipeline/db/repository.py`).
  - The backend keeps its own copy of every snapshot in SQLite.
  - The launcher ignores a Compose-only `DATABASE_URL` (`f463ea1`).
- **Verification:** 2026-09-26: analysis ran natively. 2026-10-06: saved reports persisted in
  `.local-ui-check/backend.sqlite3`, and three saved reports reopened in the browser.
- **Remaining limitations:** natively, data-pipeline's own `GET /internal/analysis/{id}` returns nothing.
  Nothing in the user flow reads it. The database file is git-ignored and local to each machine.
- **Commits:** `ef01630`, `f463ea1`.
- **Status:** fixed and verified for the native path. For Compose, see J-05.

## J-08 Undefined `_downstream_error` (regression)

- **Date / problem:** found 2026-10-06 while reading the code. No user has reported it.
- **Root cause (confirmed by code inspection):**
  - The scaffold defined `_downstream_error()`. The 2026-09-28 getaddrinfo fix (J-06) deleted it along with
    the old error helpers.
  - `backend-api/routers/parcels.py` still calls it in three places: data-pipeline collection, ml-models
    enrichment and evaluation. No definition exists anywhere in the repository.
  - **Hypothesis, not reproduced:** a non-2xx response from data-pipeline or ml-models would raise
    `NameError` and surface as a generic 500, instead of a 502 that names the service.
- **Changes:** `_downstream_error()` was defined again in `backend-api/routers/parcels.py` (`80eadd5`). It relays
  4xx and 503 replies with their status and message, and turns other failures into a 502 that names the service.
- **Verification:** `grep` found no definition before the fix. `git log -S` shows it was removed in local-only
  `a13a70b`, published in `ef01630`. On 2026-10-06, `backend-api/tests/test_reports.py::test_pipeline_errors_are_relayed_with_their_status`
  checked that a 503 from data-pipeline stays a 503 whose detail names the service and the fix. It passed.
- **Remaining limitations:** none known.
- **Commits:** introduced by `ef01630`; fixed in `80eadd5`; test added in the India milestone commit.
- **Status:** fixed and verified.

## J-09 Unsafe local launchers

- **Date / problem:**
  - `scripts/run_local.sh` and `stop_local.sh` were written on 2026-09-26 and published as WIP in `4aeaf44`.
  - On 2026-10-06 the owner reported that `run_local.sh` force-killed whatever held ports 8000, 8001, 8002 and
    5173, and seeded a demo report on every start. Both scripts needed bash, and on this machine
    `where bash` returned WSL launchers rather than Git Bash.
  - On 2026-09-28 the launcher also never returned in an automation shell: its background processes held the
    output pipe open. That was not fixed in the old script.
- **Root cause (confirmed by reading the scripts):**
  - `run_local.sh` and `stop_local.sh` ran `taskkill //PID <pid> //F` on every listener of those ports.
  - `run_local.sh` always ran `scripts/seed_ui_demo.py`.
- **Changes (`f463ea1`):** `terrascope.cmd` plus `scripts/terrascope.ps1`, with `setup`, `start`, `stop`,
  `status` and `seed-demo`.
  - Every port is checked before anything is launched. A port is reused only when it already serves the
    matching healthy TerraScope service. Otherwise `start` refuses and names the process holding it.
  - `stop` terminates only processes whose command line contains this checkout's path.
  - It loads `.env`, replaces container paths, and waits for each `/health`, printing the log tail on failure.
  - Seeding is an explicit command.
  - `.gitattributes` keeps `.cmd` and `.ps1` files in CRLF. Both `.sh` launchers were deleted.
- **Unsuccessful first version (2026-10-06):** with a foreign process on 8002, it started data-pipeline before
  it found the conflict. The `stop` that followed reported data-pipeline "not running", although `status` then
  showed it healthy (pid 35124). The launcher was changed to check every port first. A later `stop` did stop
  pid 35124. Why the first `stop` missed it was not diagnosed.
- **Verification (2026-10-06):**
  - Restart reuses healthy services, and `stop` leaves no processes behind.
  - With a stand-in foreign server on 5173, and separately on 8002, `start` refused, named the pid, started
    nothing, and the foreign process survived.
  - Services survive closing the console that launched them.
  - The PowerShell parse check passes.
- **Remaining limitations:**
  - Windows only.
  - **Hypothesis, untested:** any process whose command line contains the checkout path counts as "ours".
  - `.env.example` still mentions `scripts/run_local.sh` (J-29).
- **Commits:** `4aeaf44` (old launcher), `f463ea1` (replacement).
- **Status:** fixed and verified.

## J-10 Setup recovery on a fresh clone

- **Date / problem:** 2026-10-06. The owner had deleted the other working copy. The remaining clone had no
  `.env`, no virtual environment and no `frontend/node_modules`, and no earlier install attempt had
  completed. The website could not be run.
- **Root cause (confirmed):** nothing had been installed in this clone.
- **Changes:**
  - Created `.venv` (Python 3.11.5) with all three services' requirements, using the CPU PyTorch index.
  - Ran `npm ci` from the lockfile (87 packages).
  - Recreated `.env` from the template with every credential blank, a blank `DATABASE_URL` and
    `SATELLITE_DEMO_FALLBACK=false`.
  - Wrote the launcher (J-09). No other source changed.
  - The Python install took about 28 minutes, most of it unpacking PyTorch after the downloads finished.
    Antivirus scanning is a **hypothesis** for the delay.
- **Verification (2026-10-06):**
  - Every `/health` returns its service name, `:5173` returns 200, and CORS allows `http://localhost:5173`.
  - In the browser flow (J-01), analysis took 26 s. The report showed:
    - Sentinel-2 evidence
    - accessibility 76.94, marked "indicative only"
    - legal, flood and growth "not assessed"
    - verdict `INSUFFICIENT_EVIDENCE`
    - valuation "unavailable"
  - Tests run that day: backend 2 passed, `data-pipeline/test_etl_evidence.py` 6 passed,
    `ml-models/test_retrieval_cache.py` 6 passed, valuation 15 passed and 5 failed (no model loaded, J-18).
    Only one file per service was run, which is why `STATUS.md` shows 6/6.
  - Full unit suites on a clean export of `f463ea1`, run later the same day: data-pipeline 20 passed,
    ml-models 35 passed, backend 2 passed.
- **Remaining limitations:** `valuation/artifacts/*.joblib` is git-ignored, so a fresh clone has no model.
  Five valuation tests fail until `python -m valuation.train` is run.
- **Commits:** `f463ea1`.
- **Status:** fixed and verified.

## J-11 Seeded demo report claimed live evidence

- **Date / problem:** found 2026-09-28. The seeded UI demo report labelled hand-written values as live
  Overpass and Open-Elevation data, a NASA AppEEARS series and a MahaRERA match with a registration number that
  does not exist.
- **Root cause (confirmed):** `scripts/seed_ui_demo.py` stamped fixture values with live source labels.
- **Changes:** every evidence row and the address are labelled FIXTURE. Since `f463ea1`, seeding happens only
  through `terrascope.cmd seed-demo`.
- **Verification:**
  - 2026-09-28: the fixture validates against the snapshot schema.
  - 2026-10-06: `start` seeds nothing.
- **Remaining limitations:** reports seeded before this fix may still sit in older local databases. They are
  not in Git.
- **Commits:** local-only `e669ca8`, published in `4aeaf44`. Also `f463ea1`.
- **Status:** fixed and verified.

## J-12 UI simulated progress and placed markers at invented positions

- **Date / problem:**
  - 2026-09-09: `cd7d28d` "remove fabricated satellite and report values". Only the commit message exists.
  - From 2026-09-25: the analysis overlay advanced on a 1.2 s timer regardless of progress; the map plotted
    amenity markers at fixed offsets from the search centre; the score strip read
    `risk.accessibility_score`, which was never populated.
- **Root cause (confirmed by code reading):** placeholder UI logic.
- **Changes:** the stages follow real requests (and later drive a progress bar). Markers use the coordinates
  the connector computes. DEMO DATA banners appear, and the evidence legend distinguishes live, cached,
  upload, derived and seed data. Files: `frontend/src/pages/*`, `frontend/src/lib/api.ts`,
  `frontend/src/styles.css`.
- **Verification:** the frontend type-check and production build pass (2026-09-28). Browser runs on
  2026-09-26, 09-29 and 10-06 exercised the overlay and the report. None of them recorded a specific check of
  marker positions.
- **Remaining limitations:** marker placement has not been compared against the connector's coordinates in a
  browser.
- **Commits:** `cd7d28d`, `681c2ea`.
- **Status:** in progress (verification incomplete).

## J-13 RERA district match reported as registration

- **Date / problem:** 2026-09-22 to 09-25. `match_parcel_to_rera` set `is_rera_project=True` whenever any
  seeded project shared the parcel's district, crediting the parcel with legal safety it had not earned. It
  also returned every CSV column, which the strict schema (`additionalProperties: false`) would reject with a
  400.
- **Root cause (confirmed):** a district-level join was treated as parcel registration.
- **Changes:**
  - A district match travels as separate candidate evidence. The parcel's own status stays `null` (unknown),
    and absence from the seed is also unknown.
  - Output is projected to the schema fields.
  - Scoring keeps the three states and treats unknown as unverified.
  - Files: `data-pipeline/connectors/rera_ingest.py` and its test, `ml-models/scoring_engine/scoring.py` and
    its test.
- **Verification:** unit tests pass (data-pipeline 20 on `f463ea1`). The integration test
  `test_rera_district_match_is_never_reported_as_this_parcel_registration` passed on 2026-09-28.
- **Remaining limitations:** see J-14.
- **Commits:** `be6fb6c`.
- **Status:** fixed and verified.

## J-14 No usable RERA data for the parcels we test

- **Date / problem:** open since 2026-09-22. RERA status is always "unknown".
- **Root cause (confirmed):** `data-pipeline/data/raw/maharera_seed.csv` does not exist, and no records were
  invented. A MahaRERA seed covers Maharashtra only. It cannot speak to the Andhra Pradesh pilot (Kadapa) or to
  Tamil Nadu.
- **Changes:** the drop-in format is documented in `data-pipeline/data/raw/README.md`. Since `067d541`, a
  missing RERA record no longer subtracts legal-safety points.
- **Verification:** the 2026-09-29 source audit found the seed absent and the jurisdiction wrong.
- **Remaining limitations:** a Tamil Nadu RERA source (TNRERA) is not integrated, and no access route has been
  assessed.
- **Commits:** `79b83fa` (README), `067d541`.
- **Status:** unresolved.

## J-15 Flood Safety 50 for every parcel (terrain proxy)

- **Date / problem:** the owner reported on 2026-09-26 that flood safety was 50 for every parcel.
- **Root cause (confirmed):** the regional baseline defaulted to the parcel's own elevation, so the delta was
  always 0.
- **Attempt:** sample 16 surrounding points in one batched lookup, compare against their median scaled by
  local relief, and add a lowland term. The session measured Shimla 0, Chennai 50, Kadapa 47, Kolkata 71 and
  Kochi 97. File: `data-pipeline/connectors/elevation_dem.py`.
- **Why it was superseded:** the 2026-09-29 audit (J-17) found that terrain position is not flood evidence.
  It uses no rainfall, drainage, watercourse or hazard data, and it cannot separate coastal, river and
  rainfall flooding. The figure became the indicator `risk.terrain_relative_elevation_score`, and the method
  was renamed `estimate_terrain_relative_elevation`.
- **Commits:** `1015563`, then `067d541`.
- **Status:** superseded by J-17. Real flood indicators are part of J-28.

## J-16 Legal Safety 90 from missing land records

- **Date / problem:** 2026-09-28. A parcel with no land records scored 90/100 for legal safety and showed no
  warning.
- **Root cause (confirmed):** missing records cost only 10 risk points.
- **Attempt:** the verdict text said that legal safety was unverified, and the scores were left unchanged. The
  weighting was left to the owner.
- **Why it was superseded:** the 2026-09-29 audit removed the legal score entirely when no records support it
  (J-17).
- **Commits:** local-only `bab54ca`, published in `be6fb6c`. Superseded by `067d541`.
- **Status:** superseded by J-17.

## J-17 Scores and verdicts not supported by evidence

- **Date / problem:** 2026-09-29. Kadapa report `63188e21` showed Legal Safety 50, Flood Safety 45,
  Growth 52.25, Accessibility 83.01, WAIT and 46% confidence.
- **Root cause (confirmed):** the stored snapshot was re-run through the scoring code, which reproduced all
  six numbers:
  - Legal 50 = 100 − (10 + 20 + 20). It was derived entirely from absent evidence, counted the RERA gap twice,
    and relied on a Maharashtra seed for an Andhra Pradesh parcel.
  - Flood 45 = 100 − (50 + 4.7). This is terrain position (J-15).
  - Growth 52.25 = (50 + 5) × 0.95. That is a hard-coded default, plus 5 read off the SYNTHETIC satellite
    series (J-21), times a factor for a road type missing from the table.
  - Accessibility 83.01 came from real OSM data, but as a straight line from the centroid. The distance
    preferences were never read (J-23).
  - Confidence 46% = completeness × distance from 50. Completeness counted an all-null RERA block as present.
- **Changes:**
  - Legal returns no score, with "Legal verification incomplete" and a records checklist.
  - Flood returns null unless a real hazard source fills `risk.flood_risk_score`.
  - Growth requires observed imagery.
  - Missing factors block the composite instead of being renormalised away. The verdict becomes
    `INSUFFICIENT_EVIDENCE`.
  - Confidence is removed, and evidence coverage is shown instead.
  - Operator instructions moved from the UI to `docs/SETUP_VALUATION.md`.
  - Files: `ml-models/scoring_engine/{_assessment,_verdict,scoring}.py` and others; 15 new regression tests.
- **Verification:**
  - 2026-09-29: browser check on the re-analysed parcel. The report showed `INSUFFICIENT EVIDENCE`, three
    factors "Not assessed", no confidence percentage, and the terrain indicator labelled "not flood risk".
  - The tests pass: 35 ml-models tests on `f463ea1`.
  - 2026-10-06: the Vellore report showed the same withheld states.
- **Remaining limitations:**
  - With legal, flood and growth unscored, every real report currently ends `INSUFFICIENT_EVIDENCE`.
  - Accessibility contributes as "indicative". The session flagged this for owner review.
  - `4a01704` lets proven disqualifying legal risk produce AVOID on its own.
- **Commits:** `067d541`, `4a01704`.
- **Status:** fixed and verified.

## J-18 Synthetic valuation shown as prices for real parcels

- **Date / problem:**
  - The valuation module was built from 2026-09-25 with no real data. It has a CSV contract, a district-median
    baseline compared against a gradient-boosting model, and refusal outside coverage.
  - 2026-09-26: the owner reported that most locations showed "unavailable". The fixture covered only 8
    districts.
- **Unsuccessful approach (2026-09-26):** the synthetic fixture was expanded to 40 districts in 20 states
  (1,200 invented rows), so that fewer real places were refused.
  - Real parcels then received invented prices labelled DEMO DATA, for example ₹1,905/sq ft at Vellore and
    ₹6,396/sq ft on the seeded report. On 2026-09-28 the session observed ₹6,770/sq ft.
  - Why it changed: a banner does not make an invented price acceptable on a real parcel's report.
- **Root cause (confirmed):** the only trained model was fitted on
  `valuation/fixtures/synthetic_land_prices.csv`.
- **Changes (2026-09-28):**
  - `estimate_value` refuses with `reason: synthetic_model_only` unless `VALUATION_ALLOW_SYNTHETIC=true`.
    Demo figures are then flagged `is_synthetic`.
  - The report explains the refusal.
  - Operator instructions moved to `docs/SETUP_VALUATION.md` (`067d541`).
  - The published module (`3b34548`) already contains this gate, although its commit message mentions only the
    `is_synthetic` flag.
- **Verification:**
  - 2026-09-28: refusal confirmed against the live backend. The integration suite gave 18 passed and 2 skipped
    (the price-arithmetic tests skip because no price is produced).
  - 2026-10-06: the browser report showed valuation "unavailable".
- **Remaining limitations:** a fresh clone has no `.joblib`, so 5 valuation unit tests fail until a model is
  trained (J-10).
- **Commits:** local-only `2b8a579`, published in `3b34548`, `681c2ea`, `4aeaf44` and `0721699`. Also
  `067d541`.
- **Status:** fixed and verified.

## J-19 No real land-price data

- **Date / problem:** open since 2026-09-25. No parcel can be valued.
- **Root cause (confirmed):** the repository holds no real, sourced price observations.
- **Changes:** none. The dataset requirements and provenance rules are in `docs/SETUP_VALUATION.md`.
- **Remaining limitations:** for Tamil Nadu the candidate is TN Registration Department (TNREGINET) guideline
  values. Those are administrative floors, not market prices, and must not be mixed in unlabelled. No
  authorised integration exists.
- **Status:** unresolved.

## J-20 NASA AppEEARS satellite integration

- **Date / problem:** 2026-09-08 to 09-09. Satellite evidence was switched from Sentinel Hub to NASA AppEEARS,
  followed by fixes to task submission, downloads, Earthdata login and bearer tokens. An Earthdata URS token
  is now rejected because it is not an AppEEARS task token. Polling was capped in demo mode (150 s → 30 s →
  10 s).
- **Root cause:** not applicable. The integration was never shown working.
- **Verification:** no recorded session ran it with real Earthdata credentials. `.env` held only placeholders.
- **Why it was superseded:** Planetary Computer serves Sentinel-2 L2A with no credentials (J-22).
- **Commits:** `b0e979b`, `b608eec`, `b012404`, `e08a976`, `2bae290`, `7836e5b`, `e6cf082`, `140502f`.
- **Status:** superseded by J-22. The code remains, and it is used only when credentials are set or AppEEARS is
  selected explicitly.

## J-21 Invented satellite series as fallback

- **Date / problem:** 2026-09-09 to 09-29. The satellite fallback went through three stages:
  1. `e7c8adc` generated a deterministic NDVI/NDBI series whenever AppEEARS failed. It was on by default and
     labelled only in `source_reference`.
  2. `cd7d28d` removed it, so the chart was always empty.
  3. On 2026-09-26 it came back as a series labelled SYNTHETIC, with `seed_data` freshness, a DEMO DATA banner
     and ledger text saying the values were invented (`ef01630`).
- **Root cause (confirmed 2026-09-29):** placeholder credentials counted as configured, and `.env` forced
  `SATELLITE_PROVIDER=appeears`. Every analysis therefore took the AppEEARS path, failed, and fell back to
  invented numbers.
- **Why it was superseded:** real imagery replaced it (J-22). Placeholders no longer count as credentials.
- **Remaining limitations:** the fallback code is still in `satellite_appeears.py`. `.env.example` ships
  `SATELLITE_DEMO_FALLBACK=true`, and the Compose defaults would still reach it (J-05).
- **Commits:** `e7c8adc`, `cd7d28d`, `ef01630`, `4a01704`.
- **Status:** superseded by J-22.

## J-22 Real Sentinel-2 observations via Planetary Computer

- **Date / problem:** 2026-09-29. The report needed real imagery.
- **Changes (`4a01704`):**
  - `data-pipeline/connectors/satellite_planetary.py` reads Sentinel-2 L2A from the Planetary Computer STAC
    catalogue through anonymous SAS signing. It reads red, NIR and SWIR from the COGs over the polygon, and
    uses the scene classification layer (upsampled from 20 m to 10 m) to mask cloud, shadow, cirrus, saturated
    and no-data pixels.
  - Scene reads run concurrently. Sequential reads had taken over 40 s, overrun the deadline, and the series
    was silently dropped.
  - The result is reported as land-cover change, not growth. Growth is `not_integrated`.
- **Verification:**
  - 2026-09-29, Kadapa pilot (session report): 100 scenes matched under 35% cloud, 8 kept and 1 rejected,
    23–28 usable pixels per date. NDVI ran from 0.117 in the May dry season to 0.349 after the September
    monsoon, the expected seasonal pattern. The read took 15.7 s standalone and 17.4 s in a full analysis.
  - 2026-10-06: the Vellore browser run showed Sentinel-2 evidence.
  - 6 unit tests cover the cloud classes, the pixel floor, the NDVI/NDBI arithmetic and the cloud fraction.
- **Remaining limitations:**
  - A small parcel covers few native pixels (about 15 for the 1,544 m² pilot), so neighbouring land leaks in.
  - NDVI/NDBI cannot separate construction from cropping or clearance.
- **Commits:** `4a01704`.
- **Status:** fixed and verified.

## J-23 Accessibility measured to road midpoints; preferences ignored

- **Date / problem:** 2026-09-29.
  - The Overpass query used `out center`, so each way was measured to its own midpoint.
  - `max_road_distance_m` and `max_school_distance_m` were sent by the UI and never read.
  - Proximity was presented as access.
- **Root cause (confirmed):** found by the audit (J-17).
- **Changes:**
  - The query uses `out geom` and measures to the nearest point on the way's segments.
  - The preferences set the distance at which the score reaches zero.
  - The snapshot records the road name, access and surface tags, the school name, the method, and
    `road_access_verified=false` with an explanatory note.
  - Files: `data-pipeline/connectors/osm_infrastructure.py`, `test_osm_distance.py`,
    `ml-models/scoring_engine/scoring.py`, `docs/schema/parcel_schema.json`.
- **Verification:**
  - 2026-09-29, live Overpass, Kadapa (session report): 192 roads and 7 schools returned. The road distance
    went from 19.32 m to 18.59 m. With `max_school_distance_m` set to 5000, 3000 and 1000, the score was
    83.01, 71.94 and 60.09, where all three had previously given 83.01.
  - 5 unit tests pass.
  - 2026-10-06: Vellore accessibility 76.94, marked "indicative only".
- **Remaining limitations:** distance is a straight line from the polygon centroid to the nearest geometry. It
  is not a routed distance, and it is not evidence of a legal right of way.
- **Commits:** `386be6f`.
- **Status:** fixed and verified.

## J-24 Overpass slowness and timeouts

- **Date / problem:**
  - 2026-09-26: analyses were slow, and 4 of 6 test cities failed.
  - 2026-09-29: the PR noted that 3 of 8 test cities returned no road when the mirrors were saturated.
  - 2026-10-06: road and school evidence often missed the 35 s deadline.
- **Attempt 1 (2026-09-26, `79b83fa`):**
  - Profiling: a trivial 7-element query took 23.1 s, against 26.6 s for a 914-element query. The session
    concluded the latency was server-side queueing.
  - Changes:
    - the four lookups run in parallel under a 35 s deadline, and a missed layer is reported as a gap
    - a shared throttle and hedged failover across three whole-planet mirrors
    - non-vehicular ways excluded (5,169 → 862 elements)
    - `overpass.osm.ch` removed: it is a Switzerland-only extract that returns zero elements for India,
      which would have been recorded as "no road found"
  - Result that day (session report): 8 of 8 cities succeeded, mean 19 s, maximum 35.7 s; cached parcels took
    about 2 s.
- **Change in between:** `386be6f` moved from `out center` to `out geom` for accuracy (J-23), which returns
  larger payloads. **Hypothesis, untested:** this adds to the timeouts.
- **Observed 2026-10-06:**
  - A Vellore query through the connector's `_request_overpass` failed after 35.4 s. `overpass-api.de`
    returned HTTP 504 to GET, and the other two mirrors each hit the 25 s read timeout.
  - With a 5 s hedge, the third mirror starts at about 10 s and cannot finish inside 35 s.
  - A tiny query, and the same query sent as POST, each succeeded at other moments, and one browser analysis
    did return road and school evidence.
- **Root cause:** **hypothesis**: public-instance queueing, combined with a retry budget that does not fit the
  deadline. GET versus POST was not compared.
- **Plan:** J-28 replaces live Overpass with a local OSM extract, and keeps Overpass as an opt-in fallback.
- **Commits:** `79b83fa`, `386be6f`.
- **Resolution:** accessibility now comes from a regional local OSM store (J-28, J-30). Overpass is used only when
  `OSM_OVERPASS_FALLBACK=true` and no store is installed, so analyses no longer wait on public servers.
- **Status:** superseded by J-28 / J-30.

## J-25 RAG import error hid its real cause

- **Date / problem:** 2026-09-28. Explanations failed with `No module named 'retrieve'`.
- **Root cause (confirmed):** the `try/except ImportError` fallback for script mode also caught package-context
  failures. The real error was `No module named 'chromadb'`, which was not installed outside Docker at the
  time.
- **Changes:** the real import error now surfaces. Files: `ml-models/rag_pipeline/{main,reason,retrieve}.py`.
- **Verification:** 2026-09-28: the real cause appeared, and the tests passed. chromadb has been installed in
  `.venv` since 2026-10-06.
- **Commits:** local-only `bc3b551`, published in `09078fe`.
- **Status:** fixed and verified.

## J-26 Groq explanations never run with a real key

- **Date / problem:** Groq explanations were added on 2026-09-09. No recorded session has run them with a real
  key. `.env` held the placeholder `demo-groq-api-key` until 2026-09-29, and the key has been blank since
  2026-10-06.
- **Root cause (confirmed):** no credential has been provided.
- **Changes:** the AI budgets are bounded so that the deterministic summary is used when Groq is unavailable
  (`09078fe`).
- **Remaining limitations:** grounded explanations and citations of uploaded documents are untested.
- **Commits:** `c90d42c`, `62663f2`, `67ba72f`, `0b4078d`, `2681f14`, `09078fe`.
- **Status:** unresolved.

## J-27 Repository access and publication

- **Date / problem:** on 2026-09-28, work could not be pushed because collaborator access was pending.
  Collaborator access arrived on 2026-09-29.
- **Root cause:** the local repository came from a ZIP and had no common history with `origin/main`.
- **Changes:**
  - A sibling clone was created on a new branch, `sai/terrascope-progress`, from `origin/main` `2681f14`.
  - The tracked files moved over with `git archive`.
  - `git diff --diff-filter=D origin/main HEAD` was empty, so no teammate file was deleted.
  - The branch was pushed with no force-push, and `main` was left untouched.
- **Verification:**
  - The remote tip matched the local HEAD after a fresh fetch (2026-09-29, and again for `f463ea1` on
    2026-10-06).
  - Draft PR [riit3sh/TerraScope#1](https://github.com/riit3sh/TerraScope/pull/1) was open on 2026-10-06, head
    `f463ea1`.
- **Commits:** `1fd913f..8e52ada`.
- **Status:** fixed and verified.

## J-28 Tamil Nadu coverage and local-data milestone

- **Date / problem:** requested 2026-10-06. The goals:
  - Make TerraScope Tamil Nadu only. Place suggestions are restricted to TN. A drawn polygon is checked against
    an open TN boundary, excluding the Puducherry and Karaikal enclaves. Anything outside coverage gets an
    explicit "outside coverage" result, and no collectors run.
  - Compute accessibility from a local OSM extract, fetched by `terrascope.cmd fetch-data` (Geofabrik
    southern-zone, clipped to TN, spatially indexed, git-ignored). Overpass becomes opt-in.
  - Add flood indicators as evidence only, with no score: JRC Global Surface Water occurrence and maximum
    extent; Copernicus GLO-30 elevation and height above the nearest drain or water body; distance to rivers,
    canals and tanks (eri).
  - Verify on four parcels: Vellore city, rural Vellore, Chennai beside water, and one outside TN.
- **Confirmed so far (data-source checks, 2026-10-06):**
  - Geofabrik southern-zone: `.osm.pbf` 532 MB, containing data up to 2026-10-04T20:20:21Z. `-free.shp.zip`
    1.1 GB, `-free.gpkg.zip` 1.2 GB.
  - Planetary Computer serves `jrc-gsw` (temporal extent 1984–2020) and `cop-dem-glo-30` (30 tiles over the TN
    bounding box). Appending a collection SAS token to a COG URL returned HTTP 403, while the `sign` endpoint
    returned 206.
  - JRC's own bucket has `downloads2021` (v1.4, 2021), newer than Planetary Computer's 2020 extent. Which one
    is the "latest version" is still to be decided.
  - JRC licence: Copernicus, free of charge, with the attribution "Source: EC JRC/Google".
  - pyosmium 4.3.1 and shapely 2.1.2 have wheels for Python 3.11 on Windows.
  - Free disk space was 21 GB (J-04).
- **Changes:** under way and uncommitted when this entry was written (2026-10-06). The work spans new
  connectors (`data-pipeline/connectors/local_osm.py`, `flood_indicators.py`, `test_local_osm.py`,
  `data-pipeline/tn_data.py`), the analyze route, the snapshot schema, the frontend pages and the launcher.
  The milestone commits will list the final file set.
- **Verification:** none yet.
- **Remaining limitations:** the flood-score rule will be proposed for team approval and not enabled.
- **Commits:** none yet.
- **Outcome (2026-10-06):** delivered in `80eadd5`, `d39f627` and `d27902f`, and verified on four parcels
  (docs/STATUS.md). The same day the scope was corrected to all of India (J-30). The Tamil Nadu boundary and
  the state filter on place search were removed. The TN data became the first regional cache.
- **Status:** superseded by J-30.

## J-29 Minor open items

- `frontend/package.json` pins 14 dependencies to `latest`. `npm ci` uses the lockfile, but `npm install`
  would drift.
- `.env.example` line 2 still refers to the deleted `scripts/run_local.sh`.
- `frontend/vite.config.js` and `vite.config.d.ts` are tracked although `.gitignore` lists them. They came in
  with the scaffold.
- `docs/STATUS.md` reports 2026-10-06 unit results from one test file per service (J-10).
- **Status:** unresolved.

## J-30 Scope correction: India-wide coverage and regional caches

- **Date / problem:** 2026-10-06. The product must cover all of India, union territories included. The Tamil
  Nadu-only restriction from J-28 refused valid Indian parcels (Puducherry, Kadapa, Patna) and limited search
  to Tamil Nadu.
- **Root cause:** J-28 implemented Tamil Nadu as the product's coverage, rather than as the first regional dataset.
- **Changes:**
  - **Coverage** (`data-pipeline/connectors/regions.py`): the India outline is the union of geoBoundaries gbOpen
    IND ADM1 (36 states/UTs, DataMeet / ECI, CC BY 2.5 IN). Up to 1% of a parcel may lie outside the
    generalised boundary. States are listed with their shares, so a border parcel is never assigned to its
    centroid's state. `outside_india` is returned before any collector runs.
  - **Regions:** `fetch_data.py` (renamed from `tn_data.py`) builds `data-cache/regions/<slug>/` for any of
    the 36 states/UTs, choosing the Geofabrik India zone by `.poly` coverage. It checks disk space, reuses
    extracts and tiles already on disk, and never downloads India-wide data unasked. `tamil-nadu` bundles
    Puducherry.
  - **Collectors:** when a region is missing, accessibility and water distances report the install command,
    and every other collector still runs. GSW and DEM tiles are read remotely when they are not cached.
  - **Search and copy:** India-wide place search and UI copy.
  - **Launcher:** `fetch-data [region]` and `TERRASCOPE_DATA_DIR`.
- **Data handling:** `tn-data/` was moved, not deleted, into `data-cache/`. The previous store is kept in
  `regions/tamil-nadu/previous-build-2026-10-06/`. The new India boundary is 49 MB. The rebuilt region took
  9 minutes from the PBF already on disk, plus 28 MB of DEM tiles for Mahe and Yanam.
- **Verification (2026-10-06):**
  - **Unit tests:** state borders, enclaves, outside India, the boundary tolerance, region selection, and an
    Indian parcel with no regional cache.
  - **Live API:** six parcels (docs/STATUS.md). Puducherry was accepted with local accessibility. Kadapa and
    Patna were analysed without regional data. Colombo was rejected in 2.3 s.
  - **Browser:** Puducherry search, analysis and reopen worked. A box drawn across the Nepal border from Raxaul
    was refused ("Only 72.9% … inside India").
- **Remaining limitations:**
  - The boundary is not a Survey of India product.
  - Geofabrik's northern zone covers 41% of Ladakh and 79% of J&K as drawn.
  - Accessibility outside installed regions needs `fetch-data <region>`.
- **Status:** fixed and verified.

## J-31 Flood assessment from river flood hazard maps

- **Date / problem:** 2026-10-06. The report said "Flood assessment unavailable" even when useful evidence
  existed, and headlined an unexplained terrain score ("46/100").
- **Source checks (2026-10-06):** JRC global river flood hazard maps v2.1.2.
  - **Release and licence:** released 2026-01-12, CC BY 4.0, doi:10.2905/JRC.VD32YWG. Open HTTP download from
    the JRC FTP mirror, with no account.
  - **Format:** 3 arc-second (~90 m) tiled COG-style GeoTIFFs. Return periods 1-in-10 to 1-in-500 years, plus
    permanent-water and spurious-depth layers.
  - **Cell values (checked on real tiles):** depth is -9999 for both "no modelled inundation" and open sea, with
    no 0-depth cells. Permanent-water cells carry depths. Spurious-depth areas are flagged with 1.
  - **Earth Engine:** not used; it would need an account.
- **Changes:**
  - **Connector** (`connectors/river_flood.py`): window reads per return period, with the exact area overlap
    of each pixel with the parcel. Valid zero depth is kept separate from no-data. Permanent water is excluded.
    Flagged depths are withheld. Areas with no tile are "not modelled", and a provider failure is
    "unavailable" and not cached. Results are cached per polygon and format version. Each scenario also gives
    the share of land within 500 m modelled as flooded.
  - **Report:** `flood_indicators.components` keeps river, historical, surface water, terrain, rainfall and
    coastal separate. Flood Safety gets status `partial` with that evidence and **no score**. A new report
    panel shows the scenario table and the components. The terrain 0-100 figure was removed from the
    headline and the elevation row, which now give metres.
- **Verification (2026-10-06):**
  - **Unit tests:** no-data vs zero depth, permanent water, flagged cells, unmodelled, partial tile edge,
    provider failure, cache reuse.
  - **Live results:** Velachery was flooded from 1-in-20, 100% at 1-in-100. VIT, Kadapa and Patna were dry on
    the parcel.
  - **Patna check:** the tile read was checked independently. 65,564 of 86,400 cells around Patna are flooded
    at 1-in-100, while the parcel cell itself is dry. Hence the added within-500-m share (35%).
- **Remaining limitations:**
  - These are modelled scenarios, river-only, ~90 m, basins over ~500 km².
  - No rainfall/pluvial or coastal dataset is integrated.
  - No overall score until a combining method is validated (by design). The earlier "start at 100" rule stays
    disabled.
- **Status:** fixed and verified (evidence only).

## J-32 NRSC historical flood footprints not machine-readable

- **Date / problem:** 2026-10-06. We investigated the NRSC/ISRO Flood Affected Area Atlas of India (1998-2022)
  as an observed-inundation source.
- **Findings:**
  - **Host:** `ndrf.nrsc.gov.in` does not resolve (local DNS and the web fetcher both fail). The technical
    document is reachable at `https://ndem.nrsc.gov.in/documents/downloads/allindia_flood_techdoc.pdf`
    (6 pages). The atlas PDF (179 pages) is reachable too.
  - **Data access:** the document states "Digital spatial maps shall be hosted on National Database for
    Emergency Management (NDEM) geoportal". NDEM is an interactive viewer. The old `hydrologicaldisasters`
    page returns 404, and no download or licence for the spatial layers was found. Extracting vectors from
    its map services would be scraping a viewing service, which we do not do.
  - **Atlas content:** the atlas is cumulative 1998-2022 inundation from IRS and foreign optical/SAR imagery.
    Its disclaimer says flash floods may be missed and that rainwater accumulation may be included.
- **Decision:** not integrated. The report lists "Historical inundation (observed): not integrated", with the
  reference. Atlas text is not presented as a parcel-level assessment.
- **Status:** unresolved (needs a permitted machine-readable release, or a data request to NRSC).

## J-33 Launcher bound `stop` to `$Region` and ran `start`

- **Date / problem:** 2026-10-06. After `fetch-data [region]` was added, `terrascope.cmd stop` and
  `terrascope.cmd fetch-data` both ran `start`.
- **Root cause (confirmed):** giving `$Region` a `[Parameter(Position = 1)]` attribute made the script an
  advanced function. PowerShell then stops binding parameters without an explicit position, so `stop` bound
  to `$Region` and `$Command` kept its default, `start`.
- **Changes:** `$Command` is now `[Parameter(Position = 0)]`, with a comment explaining why.
- **Verification:** `status`, `stop` and `fetch-data` each did their own job afterwards (2026-10-06). The
  services had been healthy, so the faulty runs only reused them. No process was harmed.
- **Status:** fixed and verified.

## J-34 `partial` factor status rejected by the shared schema

- **Date / problem:** 2026-10-06. Every evaluation in the live API run returned HTTP 502:
  `score_breakdown.factors.2.status: 'partial' is not one of [...]`.
- **Root cause:** the new flood status was added to the scoring code but not to
  `docs/schema/parcel_schema.json`. The unit tests call the scoring function directly and skip schema
  validation, so they passed.
- **Changes:** `partial` was added to the enum. A test asserts that every produced factor status is allowed
  by the schema.
- **Verification:** all five Indian parcels evaluated with HTTP 200 afterwards.
- **Status:** fixed and verified.

## J-35 Integration tests wrote fixtures into the user's saved reports

- **Date / problem:** 2026-10-06. `tests/integration` posted to the live backend on :8000, so every run added
  test reports to `.local-ui-check/backend.sqlite3`. The reports from earlier runs remain there, because the
  user's database is never edited.
- **Changes:** the client fixture starts its own backend-api on a free port, with a temporary
  `BACKEND_STORE_PATH`, wired to the live data-pipeline and ml-models. On Windows it kills the whole process
  tree on teardown: the venv `python.exe` is a launcher whose child kept the temporary database open.
- **Verification:** a full run on 2026-10-06 gave 17 passed and 3 skipped. The user's snapshot count was 90 before and 90 after, and no test backend process was left running.
- **Status:** fixed and verified.
