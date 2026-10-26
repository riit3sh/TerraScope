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
| 2026-10-11 | Browser audit and fixes: local place search, boundary drawing, invalid polygons, saved-report limit, 36 s first evaluation. Listing-based valuation pipeline (blocked on permitted data). Satellite result cache. Checklist added |
| 2026-10-12 | VIT acceptance report fixes: accessibility limits and boundary distances, exact flood probabilities and coverage wording, untruncated evidence, rule-based summary with evidence citations, seasonal satellite change test over the whole catalogue, price import workflow and source-access table, RERA applicability and survey-details workflow, measured-vs-scored report |

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
| J-36 | Autocomplete sent typing to public Nominatim | fixed and verified |
| J-37 | Workspace boundary defects (default box, re-fly, unsaveable edits, lost boundary) | fixed and verified |
| J-38 | Invalid polygons analysed or misreported | fixed and verified |
| J-39 | Saved-reports list capped at 50 | fixed and verified |
| J-40 | First evaluation after start took 36 s | fixed and verified |
| J-41 | Satellite collection repeated on every analysis | fixed and verified (repeat analyses); cold path open |
| J-42 | Listing-based valuation pipeline | in progress (blocked on permitted data) |
| J-43 | Flood panel prose-heavy | fixed and verified |
| J-44 | Upload ledger claimed retrieval that was not running | fixed |
| J-45 | Browser verification limits in the app's pane | unresolved (tooling) |
| J-46 | Accessibility limits looked ignored; distances only from the centroid | fixed and verified |
| J-47 | Flood probabilities (1-in-75 shown as 1%) and coverage claims | fixed and verified |
| J-48 | Surface-water sentence truncated in saved reports | fixed and verified |
| J-49 | "Grounded AI explanation — 0 citations" on a rule-based summary | fixed and verified (deterministic path) |
| J-50 | Satellite: 100-scene search limit, uncalibrated "confidence", offset, mask grid, tile edge | fixed and verified |
| J-51 | Background reads after deadline timeouts saturated the link | fixed and verified |
| J-52 | Price importer completed; no permitted dataset for the acceptance parcels | importer fixed and verified; live prices blocked |
| J-53 | Legal/RERA applicability, survey details and typed documents | fixed and verified (no external source integrated) |
| J-54 | Report clarity: measured vs scored, heading, duplication, refresh | fixed and verified |
| J-55 | Cold and warm analysis timings | measured |

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
- **Update 2026-10-11:**
  - Licensed and open sources were researched; no permitted dataset was found (`docs/SETUP_VALUATION.md`).
  - The valuation path was rebuilt around a provenance contract and comparables, so real rows can be loaded
    without code changes (J-42).
  - The exact blocker is a licensed listing or registration feed (a paid decision), owner or broker
    permission, or an authorised bulk export from a registration department.
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

## J-36 Autocomplete sent typing to public Nominatim

- **Date / problem:** 2026-10-11. Every pause while typing in the search box sent a request through
  `/api/v1/search/geocode` to `nominatim.openstreetmap.org`. The Nominatim usage policy forbids autocomplete.
- **Root cause (confirmed in the browser):** the suggestions effect called the same endpoint as explicit search,
  and that endpoint proxied Nominatim.
- **Changes:**
  - `fetch-data` builds `data-cache/places/places.sqlite`: an FTS5 prefix index of 733,958 names. Sources are
    the GeoNames IN gazetteer and Indian postal codes, CC BY 4.0. Indexed: states, UTs, districts, towns,
    villages, localities, colleges, stations, lakes and PIN codes. ASCII display names, filtered alternate
    names (Madras, Bombay, Cuddapah) and acronyms (VIT, IIT).
  - The new `/api/v1/search/suggest` reads only this index and returns 503 when it is missing.
    `/api/v1/search/geocode` (explicit Search) tries the index first, then one rate-limited Nominatim query.
  - Frontend: a 120 ms debounce; a newer keystroke aborts the older request; GeoNames attribution;
    approximate PIN locations are labelled.
- **Verification (2026-10-11):**
  - Browser: typing "katpadi vel" and "velach" sent only `/search/suggest`.
  - The UTs (Leh, Kavaratti, Port Blair, Silvassa, Daman, Chandigarh, Puducherry) were found.
  - Over HTTP: p50 2.9 ms, p95 24.6 ms (n=100).
  - 4 backend tests build a small index with the real builder; any network call fails the suggest endpoint.
- **Remaining limitations:** the data is points, not boundaries. District names follow GeoNames and lag
  recent splits. "vit" alone ranks a village named Vit first.
- **Commits:** `6ba3e51`, `8f9119a`.
- **Status:** fixed and verified.

## J-37 Workspace boundary defects found in the browser

- **Date / problem:** 2026-10-11, all reproduced in the browser:
  1. The workspace pre-filled an invented ~96.6 ha box, which could be analysed and was labelled
     "USER-DEFINED".
  2. After each vertex or edit the map flew back to zoom 14.
  3. The Edit mode's Save/Cancel lived in the hidden Leaflet-draw toolbar, so an edit could never be
     committed.
  4. The Draw/Edit/Reset bar covered the zoom buttons.
  5. Going to the report and back replaced the drawn boundary with the default box.
  6. After a mouse pick, Enter did nothing, because focus had left the input.
  7. The suggestion list opened underneath the saved-reports cards.
- **Root causes:**
  - (2) `Focus` depended on a centre array rebuilt every render.
  - (3) CSS `.leaflet-draw{display:none}`.
  - (5) the boundary state lived in a component that unmounts.
  - (7) both sections had `z-index:1`.
- **Changes:**
  - The boundary is lifted to `App` and starts empty; Clear replaces Reset; Analyze stays disabled until a
    boundary exists.
  - `Focus` depends on the coordinates.
  - Only the Leaflet-draw buttons are hidden, so its Finish/Cancel/Save actions show.
  - The control bar moved; the input is refocused after a pick; the search section is raised above the
    saved reports.
- **Verification (2026-10-11, browser):** drew a 0.33 ha Katpadi plot (map stayed at the user's zoom); edited it
  to 0.54 ha and saved; cleared; redrew; went to the report and back with the boundary kept. The list opens
  above the cards (screenshot).
- **Remaining limitations:** Leaflet-draw needs a mouse move before each click (automation only). From a
  reopened saved report, "Workspace" returns to search.
- **Status:** fixed and verified.

## J-38 Invalid polygons were analysed or misreported

- **Date / problem:** 2026-10-11 API probes found:
  - a self-intersecting bowtie was analysed;
  - a 2°×2° box (4.8 million ha) was analysed as a "parcel";
  - a zero-area polygon and a longitude of 279° were reported as "outside India".
- **Changes:**
  - The shared validator `InfrastructureClient._validate_polygon`, used by every analysis, rejects
    non-finite or out-of-range coordinates, zero area (checked on the convex hull, because a symmetric
    bowtie's signed area cancels to 0) and invalid (crossing) outlines.
  - `build_evidence_snapshot` refuses boundaries over `MAX_PARCEL_AREA_HA` (default 1,000).
- **Verification:** each probe now gets HTTP 400 with a sentence in under 0.6 s. There are 5 regression tests.
- **Status:** fixed and verified.

## J-39 Saved-reports list capped at 50

- **Date / problem:** 2026-10-11. The list offered "Show all 50 reports" while the store held 91 parcels. 41
  reports could not be opened from the UI.
- **Root cause:** `GET /api/v1/parcels` defaulted to 50, and the frontend did not pass a limit.
- **Changes:** the default is 1,000 (cap 5,000), and the frontend asks for 1,000.
- **Verification:** the audit store listed 95, and the normal store serves 91.
- **Status:** fixed and verified.

## J-40 First evaluation after start took 36 s

- **Date / problem:** 2026-10-11. In the browser, the first analysis spent 36.0 s in `/evaluate`. Later
  evaluations took 0.45 s.
- **Root cause (measured):** `pipeline.evaluate_snapshot` imports `rag_pipeline.reason`, which imported
  `retrieve`, which imports chromadb and sentence-transformers/torch. That import took 9.7 s warm, more when
  cold, even with no Groq key, when the function returns at once.
- **Changes:** the retrieval import moved into `generate_grounded_answer`, the only function that uses it.
- **Verification:** the import now takes 0.45 s. The first evaluation after a restart took 557 ms in the browser.
- **Status:** fixed and verified.

## J-41 Satellite collection repeated on every analysis

- **Date / problem:** 2026-10-11. The new per-collector timings (`metadata.collection_timings_ms`) showed
  Sentinel-2 collection taking 9.4-15.8 s on every run, cold or warm. It was the slowest collector.
- **Findings:**
  - The default Planetary Computer client cached only its SAS token. The AppEEARS and Sentinel Hub caches are
    not on the default path.
  - GDAL cloud-read options (no directory listing on open, `.tif` only, VSI cache) cut a standalone series
    from 17-23 s to 11.5-12.4 s, with identical observations. The service already had them, but only as a
    side effect of `flood_indicators` being imported first.
  - Read workers: 12 took 10.5-12.2 s and 8 took 11.5-13.8 s (n=3 each), with identical output.
  - Remaining: remote DEM reads for parcels without a regional cache take 3.7 s alone, and 7-18 s while
    competing with satellite reads.
- **Changes:**
  - Per-scene measurements are cached by scene id, polygon fingerprint, masking parameters and algorithm
    version. Scenes are immutable: reprocessing publishes a new id.
  - Catalogue searches are cached and refreshed after 6 h for windows ending within 60 days, and after
    30 days otherwise.
  - Failed reads are never stored, and are now reported as making the series partial.
  - Storage: SQLite in WAL mode with a busy timeout, LRU row caps, and `SENTINEL_CACHE=off`.
  - Observations are ordered by (date, scene id), so ties no longer depend on read order.
  - The GDAL import is explicit, and there are 12 workers.
  - The evidence row says "cached" with the catalogue age when it was reused.
- **Verification (2026-10-11):**
  - Same 6 parcels and session; before = cache off, 2 runs; after = cache on, 3 runs.
  - Warm analysis median: 10.9 s → 0.66 s. Satellite collector warm: 9.4-14.3 s → 0.08-0.11 s.
  - Cold median: 13.9 → 12.4 s, essentially unchanged.
  - Satellite and flood fingerprints were identical across every run.
  - 7 new unit tests: reuse, failed reads not stored, unusable scenes stored, refresh of recent catalogues,
    key sensitivity, opt-out, eviction under concurrent writers.
  - The integration suite now takes 82 s (6 min on 2026-10-06).
- **Remaining limitations:** cold analyses are still bound by network reads. DEM/GSW remote results are not
  cached. Caching reduces network time; it does not change algorithmic complexity.
- **Commits:** `8f9119a`.
- **Status:** fixed and verified for repeat analyses; cold-path latency is still open.

## J-42 Listing-based valuation pipeline (replaces the synthetic model)

- **Date / problem:** 2026-10-11. Valuation served a gradient-boosting model that had only ever been trained on
  synthetic rows (J-18, J-19). It had no provenance fields and no way to keep asking prices, sales and
  guideline values apart.
- **Changes:**
  - `valuation/dataset.py`: an observation contract with source and record id/URL, reuse basis, price type,
    observed and retrieved dates, original price and unit, area and unit, category, land use, and location
    precision.
  - Cleaning: currency, unit, plausibility, built-property and location rules, each drop counted by reason.
  - De-duplication: re-listings by any source, at any date, become one property, with an optional
    `property_ref`.
  - `valuation/comparables.py`: the median of nearby, recent, similar-size comparables of the same use and
    price type. Its spread is labelled as the comparables' own, not an interval. Refusals are explicit; for
    example, a campus is never valued from house plots.
  - `valuation/evaluate.py`: grouped temporal and geographic holdouts. Metrics: MAE, RMSE, median APE,
    ±10/20/30%, coverage and spread containment. A gradient-boosting comparison from 300 training rows. Below
    30 test estimates the result is "not yet validated".
  - UI: "Listing-based estimated price range", comparables with provenance, and uncertainty reasons.
    Refusals are explained without operator instructions.
  - The synthetic fixture, model artifact and `train.py` were removed.
- **Data access research (2026-10-11):** no permitted dataset was found; see `docs/SETUP_VALUATION.md`.
  - The portals' terms pages refused automated access; they have no API or licence.
  - Registration and guideline portals offer lookups behind captchas.
  - OpenCity has Bengaluru 2023 guidance-value PDFs, marked public domain. They are reference values only and
    were not imported.
- **Verification:**
  - 48 unit tests on synthetic rows, including regression tests restored from the previous contract.
  - Integration: refusal contract, and a 400 for bad input with no data.
  - Browser: the refusal card on the Katpadi and Velachery reports.
- **Remaining limitations:** there is no real data, so no live price exists and quality is "not yet
  validated". There is no time adjustment, and the GBM's hyperparameters are fixed.
- **Status:** in progress (blocked on permitted data).

## J-43 Flood panel was prose-heavy

- **Date / problem:** 2026-10-11. The panel repeated long summaries. The structured measurements already in the
  snapshot (surface water, terrain, water distances) were not shown as numbers.
- **Changes:** a table with one line per mechanism and its measurement: first flooded return period, share
  and depth, surroundings, ever-wet share, elevation relative to water, and distances. Scenario table, sources
  and method are behind "details". Unknown mechanisms read "Unknown, not safe". The table stacks on narrow
  screens.
- **Verification:** browser, Katpadi (no river inundation; +0.3 m above a stream 532 m away) and Velachery
  marsh edge (100% of the parcel at 1-in-10, up to 4.96 m; lake 178 m).
- **Status:** fixed and verified.

## J-44 Upload ledger claimed retrieval that was not running

- **Date / problem:** 2026-10-11. An uploaded TXT was listed as "indexed for grounded retrieval", but retrieval
  needs `GROQ_API_KEY`, which is not set.
- **Changes:** without the key, the ledger says the text was extracted and stored, is not read or cited by any
  analysis, and is unverified.
- **Status:** fixed (verified by unit tests and code path; the wording was not rechecked in the browser).

## J-45 Browser verification limits in the app's pane

- **Date / problem:** 2026-10-11. In the app's built-in browser pane, screenshots often timed out, or came back
  black, tiled or stale, at an emulated 1440×900 viewport. A network outage also interrupted one session.
- **Handling:** checks used DOM and text reads, and network and console logs from a fresh tab (no errors, every
  request 200). Screenshots were taken at the pane's own width when it rendered. This is a tooling limitation,
  not a product defect.
- **Status:** unresolved (tooling).

## J-46 Accessibility limits looked ignored, and distances came only from the centroid

- **Date / problem:** 2026-10-12, VIT acceptance report (snapshot 568d1f42, 2.75 acres).
  - The accessibility factor said `max_road_distance_m` and `max_school_distance_m` were "accepted but not
    applied".
  - The UI had no control for either limit.
  - Every distance was measured from the parcel centroid.
- **Root cause (confirmed by tracing UI → API → scoring):**
  - The scoring code had applied both limits since `386be6f` (J-23); 90.25 = (95.83 × 1 + 87.59 × 2.1) / 3.1
    with limits of 3,000 m and 5,000 m.
  - The limitation text was stale copy from before that fix.
  - The workspace drawer sent fixed defaults with no control. The API accepted any preference dict, so an
    unknown key or a negative limit was silently dropped.
- **Changes:**
  - **Collection:** the local OSM store also measures from the drawn boundary
    (`nearest_road_distance_from_boundary_m`; 0 m when a mapped way touches or crosses the parcel), alongside
    the centroid.
  - **Scoring (`accessibility_v2`):**
    - The boundary distance is used when recorded; older snapshots use the centroid, and the factor says so.
    - The factor carries `details`: each feature's distance, where it was measured from, the limit, the
      sub-score and the weight.
    - A feature not found inside the 5 km search scores 0 only when the search covered the user's limit;
      otherwise it is left out.
  - **API:** a `Preferences` model with `extra="forbid"`. Limits must be 100-20,000 m, and importances and
    the RERA requirement are enums. Anything else gets a 422.
  - **UI:**
    - Limit sliders in the workspace drawer and in Scenario mode, which also has the importance selects.
    - The factor shows a distance/limit/sub-score table.
    - The legal-access caveat is kept.
  - Files: `connectors/local_osm.py`, `etl_pipeline.py`, `scoring_engine/scoring.py`, `_assessment.py`,
    `routers/parcels.py`, `Report.tsx`, `ParcelWorkspace.tsx`, schema.
- **Verification (2026-10-12):**
  - **API, fresh VIT analysis (exact polygon, audit store):**
    - Road 77 m from the boundary (125 m from the centroid), school 556 m (621 m).
    - With 3,000 m / 5,000 m limits: score 91.64, contribution 22.91.
    - With 500 m / 1,000 m limits: score 57.39, contribution 14.35.
    - The stored snapshot was byte-identical after the re-evaluations.
    - The valuation response was identical before and after the preference change.
    - A limit of -5 m, an unknown key or an unknown importance: 422, with nothing forwarded to ml-models.
  - **Browser:** Scenario mode moved the limits from 500/1,000 m to 3,000/5,000 m, and accessibility went from
    57.39 to 91.64 on the same snapshot.
  - **Browser, new Katpadi plot:** road 0 m from the boundary (a mapped way crosses it), 40 m from the centroid.
  - **Tests:** 4 ML regression tests on the acceptance snapshot, and 1 backend test (limits forwarded; bad
    values rejected).
- **Remaining limitations:** straight-line proximity, not routed travel; not evidence of legal or physical
  access. The boundary is user-drawn, not cadastral.
- **Commits:** `4bdf945` (evidence, scoring, API), `059808d` (report UI).
- **Status:** fixed and verified.

## J-47 Flood probabilities and coverage claims

- **Date / problem:** 2026-10-12, VIT report.
  - The 1-in-75 scenario showed "1%".
  - The caption said "100% of the parcel assessed".
  - The glance table said 1% observed water while the source text said 1.5%.
  - "Within 500 m" was used for what is the parcel plus a 500 m ring.
  - The NRSC atlas was described as having "no machine-readable release".
- **Root causes (confirmed):**
  - **AEP:** `toFixed(p < 0.01 ? 1 : 0)` rounded 1.33% to 1%.
  - **Rounding:** `pct()` rounded 1.49% to 1%.
  - **Coverage:** "assessed" meant only that hazard-map cells were read for the whole parcel.
  - **NRSC:** the statement went further than the J-32 investigation supported.
- **Audit of the river connector:**
  - Tiles and parcel are both EPSG:4326 windows.
  - Pixel weights are the exact polygon overlap, in local metres.
  - Nodata (-9999) is "no modelled inundation" and is never written as 0 m depth.
  - Permanent water is excluded; flagged cells count as flooded with depths withheld.
  - The surroundings are `buffered(parcel, 500)`, i.e. the parcel plus the ring; permanent water is excluded
    from the denominator.
  - Parcel area: 11,106 m² in the connector, 11,114 m² geodesic (a 0.07% difference).
- **Changes:**
  - AEP is exact (`100 / return period`: 10, 5, 2, 1.33, 1, 0.5, 0.2%) and labelled "annual exceedance
    probability of the modelled event, not the probability that this parcel floods".
  - Percentages show one decimal below 10%.
  - "None modelled" replaces "0%" for parcel cells with no modelled depth.
  - River results record `model_cells_overlapping_parcel` and `model_cell_area_m2` (`RESULT_FORMAT` 3, so
    only new results carry them). VIT: 6 cells of about 0.8 ha for a 1.1 ha parcel.
  - **Method notes:** "Coverage", "Probabilities" and "Surroundings", in one expandable section.
  - **Report layout:**
    - one headline ("River flood exposure assessed; other mechanisms incomplete");
    - the compact mechanism table;
    - one "Scenarios, sources and method" section;
    - the flood factor card now points to the panel instead of repeating it.
  - The checklist lists only what is missing (rainfall/pluvial, coastal, historical), not the river map that
    was used.
  - NRSC wording: "No permitted machine-readable source integrated", with what was investigated and when.
  - No flood score was added, and missing mechanisms still read "unknown, not safe".
- **Verification:**
  - **Browser, old VIT report:** 1-in-75 reads 1.33%, surface water 1.5% in both places, NRSC wording
    corrected.
  - **Fresh VIT run:** 6 cells, 8,330 m² each.
  - The unit and integration suites pass.
- **Commits:** `4bdf945` (evidence, scoring, API), `059808d` (report UI).
- **Status:** fixed and verified.

## J-48 Surface-water sentence truncated in saved reports

- **Date / problem:** 2026-10-12. The surface-water evidence ended "...urban street flooding a".
- **Root cause (confirmed in stored data):** `[:500]` slices in `etl_pipeline.py` cut composed summaries before
  they were stored. The schema has no length limit, and the API and UI passed the text through unchanged.
- **Changes:**
  - All composed-summary slices removed; error strings are still bounded.
  - Old snapshots are not rewritten. The UI marks any summary that ends mid-sentence as "cut off when this
    report was saved", and the full figures are shown from the structured fields.
- **Verification:**
  - Regression test: the surface-water summary is longer than 500 characters and ends with its final sentence.
  - New snapshots carry the full text.
- **Commits:** `4bdf945` (evidence, scoring, API), `059808d` (report UI).
- **Status:** fixed and verified.

## J-49 "Grounded AI explanation — based on 0 citations"

- **Date / problem:** 2026-10-12. The rule-based summary was labelled "grounded AI explanation" with 0
  citations.
- **Root cause (confirmed):** `GROQ_API_KEY` is empty, so the text was always `result["reasoning_summary"]`.
  Citations came only from Groq.
- **Changes:**
  - **`explanation_source`** on the verdict: `deterministic` or `ai`. "AI explanation" is shown only when an
    AI call returned text.
  - **`ml-models/citations.py`:** deterministic evidence references, each claim tied to the evidence row that
    holds its figure:
    - accessibility;
    - river model;
    - surface water;
    - terrain;
    - the seasonal change test (v2 only).
    Absences are not cited.
  - **Uploaded PDFs** keep page breaks (form feed). The user's survey number (with subdivision, or after a
    survey-number label) and village are searched per page and cited as "filename, page N".
  - **Ledger wording:** a document is searched for those identifiers, and finding them does not verify title.
- **Verification:**
  - Fresh VIT evaluation: 5 references, every `evidence_id` present in the snapshot.
  - **Browser, synthetic 3-page PDF:** survey 123/4A and village Brammapuram cited "page 2". Legal stayed
    unscored ("user-provided, not verified").
  - Unit tests cover this. The AI path is still untested, because no key is configured.
- **Commits:** `4bdf945`, `059808d`.
- **Status:** fixed and verified (deterministic path).

## J-50 Satellite change: truncated search, uncalibrated "12% confidence", misread pixels

- **Date / problem:** 2026-10-12. The VIT report said "no change — 12% confidence" from 8 observations starting
  2025-04-07, in a window starting 2024-10-12.
- **Root causes (confirmed):**
  1. **Truncated search:** the STAC search returned only its first page (the newest 100 scenes). The window
     held 136; the 36 older scenes were never considered (checked live).
  2. **"Confidence":** 12% was half the mean R² of straight lines fitted through all dates. That is
     uncalibrated, monsoon and dry season were mixed, and ambiguous movement was filed as "no change".
  3. **Offset:** reflectance was used as raw DN. Processing baseline ≥ 04.00 adds 1,000, which biases NDVI and
     NDBI towards 0.
  4. **Grid:** SCL and B11 were read on their own 20 m crops. The cloud mask could be off by one 10 m pixel,
     and NDBI averaged SWIR over cloudy pixels.
  5. **Tile edge:** tile T44PLV ends inside the VIT parcel. Those scenes saw 36 of 134 pixels yet counted as
     0% cloud.
- **Changes:**
  - **Catalogue:** every page is read (up to 1,000 scenes), with the STAC `fields` filter (117 KB instead of
    ~550 KB per page). Truncation is recorded.
  - **Selection:** one scene per quarterly season anchor, repeated each year, so every date has a same-season
    partner 365 days later.
    - Only scenes whose footprint contains the parcel are used.
    - At least 50% of the parcel's full footprint must be clear (counted on the 10 m grid even beyond the
      tile's edge).
    - Alternates are read only for anchors that failed.
  - **Measurement:** offset removed; SCL and B11 resampled onto the 10 m crop grid; bands read two at a time.
    `ALGORITHM_VERSION` `s2l2a-ndvi-ndbi-3`, so old cache entries are not reused.
  - **Change test `seasonal_pairs_v2`:** pairs a year apart in the same season.
    - "No change" only when every pair stays within ±0.05.
    - A change class needs every pair to move the same way, with a median of at least 0.10.
    - Otherwise the result is "inconclusive".
    - No confidence percentage. `change_method` records the pairs, the differences and the reason.
  - **Provenance:** the snapshot stores per-observation scene id, anchor, clear and full pixel counts, cloud
    fractions and offset, plus collection diagnostics.
  - **Old reports** read "no clear trend (v1 method)". The stored figure is explained as a trend-fit number,
    and the late first image is explained by the 100-scene limit.
- **Verification (2026-10-12):**
  - **Fresh exact-polygon VIT run:**
    - 136 scenes matched, 67 skipped as not covering the parcel.
    - 7 observations, each 134/134 pixels clear, from 2024-12-23 to 2026-08-10.
    - No usable scene near the 2025-08-26 (monsoon) anchor.
    - 3 same-season pairs, NDVI changes −0.043, −0.020, +0.005; NDBI +0.033, +0.032, +0.007.
    - Result: no material change.
  - **Cold benchmark (shifted polygons):** Katpadi plot, Kadapa and Patna came out "inconclusive";
    Velachery, Puducherry and the VIT campus part "no change".
  - **A/B on the VIT polygon, cache off, same network, interleaved:** old connector 52.1 s and 36.9 s (1-2
    failed reads); new 22.6 s and 28.0 s (no failures).
  - **Cache reuse:** the series repeated exactly, and the evidence row says "cached" with the catalogue age.
  - **Tests:** 24 satellite unit tests (paging, bounded paging, anchors, offset, clear-pixel SWIR, tile edge,
    footprint filter, alternates, cache) and 8 change-test tests.
- **Remaining limitations:**
  - The thresholds are rules, not calibrated against labelled change.
  - Monsoon anchors often have no clear scene.
  - 10 m pixels on a ~1 ha parcel include neighbouring land at the edges.
- **Commits:** `4bdf945` (evidence, scoring, API), `059808d` (report UI).
- **Status:** fixed and verified.

## J-51 Self-inflicted network saturation after evidence-deadline timeouts

- **Date / problem:** 2026-10-12, during the cold benchmark.
  - Every new parcel's satellite collection hit the 35 s deadline.
  - Geocoding took up to 96 s, and Planetary Computer returned SSL EOFs.
  - With the services stopped, the link was normal again: Planetary Computer ~1 s, google 0.65 s.
- **Root cause (measured):**
  - A collection past the deadline kept reading in the background (`pool.shutdown(wait=False)`).
  - Back-to-back analyses stacked those reads. With no request in flight, the data-pipeline held 26 open
    connections and pulled 0.5-0.8 MB/s over Wi-Fi.
- **Changes:**
  - A process-wide cap of 8 concurrent scene reads (`SENTINEL_MAX_CONCURRENT_SCENES`).
  - `give_up_at`: once the evidence deadline passes, no new scene read or alternate wave starts. In-flight
    reads finish and are cached.
  - A timed-out collection is now recorded as `collection.status = timed_out`. The report says so, instead of
    "no usable satellite observations".
  - Successful geocoding lookups are cached per address for the life of the process, as the Nominatim policy
    asks. This was the slowest warm step (0.5-6.4 s).
- **Verification (2026-10-12, 7 parcels in India, shifted so run 1 was cold):**
  - Cold analysis median 13.6 s (4.9-21.8 s), with satellite completing for every parcel.
  - Warm median 0.43 s.
  - Kadapa and Patna warm runs took 8.5 and 9.5 s: those regions have no local tiles, and their remote DEM
    and GSW reads are not cached yet (J-41).
  - 2 regression tests (cap, no reads after the deadline).
- **Commits:** `4bdf945` (evidence, scoring, API), `059808d` (report UI).
- **Status:** fixed and verified.

## J-52 Price data: importer completed; no permitted dataset for the acceptance parcels

- **Date / problem:** 2026-10-12. The report repeated "no price estimate" three times. The importer had no
  per-row explanation, no preview and no UI.
- **Changes:**
  - **Report:** one reason plus one next step, and a price-basis selector.
  - **Preview (`valuation/importer.py`):**
    - per-line rejection reasons and duplicate links (same record, or a re-listing);
    - stale, future-dated and coarse-location flags;
    - groups by price type × land use × category;
    - sources and their permissions;
    - normalised rows.
  - **Commit:** needs a permission confirmation; appends only rows that passed; keeps a backup; re-validates
    the combined file before replacing it.
  - **API:** `/api/v1/valuation/import/preview|commit`. **UI:** the "Price data" page. **Command line:**
    `python -m valuation.dataset` prints per-row reasons.
  - The estimator, the refusals and the no-pooling rules are unchanged.
- **Source research (browser, 2026-10-12):** see the table in `docs/SETUP_VALUATION.md`.
  - **TNREGINET:** its copyright policy forbids reproduction without the Registration Department's permission.
    The guideline-value lookup has no bulk download.
  - **data.gov.in:** no guideline, circle-rate or land-price dataset.
  - **99acres:** its terms require IEIL's prior written consent and forbid crawlers.
  - **Housing.com:** its terms claim the data compilations.
  - **MagicBricks:** not readable from here.
  - **OpenCity:** Bengaluru 2023 only.
- **Verification:**
  - **Browser, synthetic CSV, audit-only price file:**
    - 11 rows: 3 rejected (missing permission, built property, implausible ₹3/sq ft), 1 repeated record, 1 stale.
    - Commit added 8 rows.
    - The report's "registered sale prices" basis then showed a sale-based range from 6 comparables, listed with
      source, record, date, ₹/sq ft, area, distance, precision and permission.
    - The VIT campus was refused (`area_outside_support`).
  - 4 new unit tests.
  - The synthetic file was removed afterwards. The real `data-cache/valuation/observations.csv` was never
    written.
- **Remaining:** no real price data. No prediction metric exists; none is quoted.
- **Commits:** `4bdf945`, `059808d`.
- **Status:** importer fixed and verified; live prices blocked on permitted data.

## J-53 Legal and growth status

- **Date / problem:** 2026-10-12.
  - The legal factor said "The only registration dataset present is a MahaRERA seed" for a Tamil Nadu parcel;
    no seed is even configured.
  - The ledger row was titled "MahaRERA static seed dataset".
  - The state read "this parcel's state", although the boundary file gives Tamil Nadu.
- **Changes:**
  - **RERA:**
    - The RERA row names the parcel's state authority as not integrated.
    - The MahaRERA seed is used only for Maharashtra.
    - A district match is never attempted against another state's seed.
  - **State:** filled from the boundary polygon when geocoding gives none, ASCII-normalised ("Tamil Nadu").
  - **Survey details:** the report takes state, district, taluk, village, survey and subdivision numbers. Missing
    state, district or village is flagged as ambiguous.
  - **Documents:** typed uploads (patta/chitta, EC, sale deed, approval, FMB, other).
  - **Never verification:** these travel as `user_land_details`, "user_provided_unverified", and never populate
    `land_records`. Legal Safety stays unscored.
  - **Growth:**
    - The wording keeps land cover separate from investment growth.
    - The checklist names the data a growth score would need: registered sale counts by village or
      sub-registrar office, master-plan zoning and approved layouts, committed infrastructure, and
      population/employment change.
- **Verification:** see J-49 for the browser check. The integration test now asserts the Tamil Nadu RERA
  wording. Backend tests cover the claims, the 404/422/400 paths, and that claims never reach `land_records`.
- **Commits:** `4bdf945`, `059808d`.
- **Status:** fixed and verified. No land-records or RERA source is integrated (external).

## J-54 Report clarity: measured vs scored, heading, duplication

- **Date / problem:** 2026-10-12.
  - "75% of evidence fields collected" sat beside "25% of weighting evidenced" with no explanation.
  - The heading was the full Nominatim address.
  - Price, flood and verdict text was repeated in several places.
- **Changes:**
  - **Figures:** "Scored: 25% of your weighting (Accessibility)" and "Measured: 9 of 12 evidence fields", with
    both denominators in an expandable section. New snapshots list each counted field.
  - **Heading:** the place name, with the full address beneath it.
  - **Recommendation:** "INSUFFICIENT EVIDENCE · recommendation withheld"; scored factors are listed first.
  - **Unscored factors** appear in the contributions list as "no score · weight".
  - **Duplicate "FINAL" box** removed.
  - **Older evaluations:** a banner offers "Re-evaluate with current methods", which appends a new evaluation
    and keeps the old one.
  - **Refresh:** the open report is in the URL hash (`#report/<parcel>`), so a browser refresh reopens it.
  - **Bugs found and fixed in passing:**
    - the new Price-data button sat under the decorative grid and could not be clicked;
    - two drawer controls had no accessible name.
- **Verification (browser):**
  - The old and new VIT reports, a refresh, and a fresh tab: no console errors, every API call 200.
  - The earlier `createRoot` warnings came from Vite hot reloads during editing.
  - Screenshots were partial because of the pane size (J-45); the rest were DOM/text checks.
- **Commits:** `4bdf945` (evidence, scoring, API), `059808d` (report UI).
- **Status:** fixed and verified.

## J-55 Cold and warm analysis timings, 2026-10-12

- **Method:** `scripts/benchmark.py --runs 2 --offset-deg 0.0009` (every polygon shifted ~100 m, so run 1 is
  cold for scenes, catalogue and river results). Seven parcels in India plus Colombo, on the audit store, on
  the same Wi-Fi link. The exact VIT polygon was measured separately.
- **Results:**
  - Cold median 13.6 s (4.9-21.8 s); warm median 0.43 s; evaluation p50 0.26 s; reopen p50 9 ms.
  - The warm exact VIT polygon took 0.49 s (1.22 s on the first run after a restart, before its geocode is cached).
  - Earlier on the same day, before J-51, cold runs hit the 35 s deadline with satellite dropped.
  - 2026-10-11 reference: cold 12.4 s, warm 0.66 s.
- **Status:** measured.

## J-56 Buy or wait: a decision from the history of the plot and its surroundings

- **Date / problem:** 2026-10-20. The product's aim is to tell a buyer whether to buy now or wait, from the
  history of the plot and the land around it. It never did: all 58 saved evaluations in the user's store were
  `INSUFFICIENT_EVIDENCE`. Legal and growth always carried weight with no possible score (no land-records
  source; growth was refused from NDVI/NDBI, J-53), so every verdict was withheld.
- **Root cause (confirmed):** a weighted factor with no score withheld the verdict, and two of the four could
  never be scored. Growth had no evidence about the *surroundings*: only the plot's own Sentinel-2 indices.
- **Changes:**
  - **New evidence, India-wide, no account:** `data-pipeline/connectors/land_cover_history.py` reads Impact
    Observatory / Esri 10 m Annual Land Use Land Cover v2 (2017-2023, CC BY 4.0) from Planetary Computer. Per
    year it records the plot's own class shares and the built-up share within 1 km of the plot edge and 1-3 km
    away, then fits a least-squares trend (points a year) so one misclassified year cannot swing it. Years
    where cloud or a tile edge hides more than half a zone are dropped. Tiles are read in parallel; results go
    into the existing 30-day parcel-result cache. One collection token is reused (per-file signing returned
    429), and 429/5xx responses are retried, honouring Retry-After.
  - **Area growth is scored** from the 1 km trend: +2 points of built land a year scores 100 (a rule, not
    calibrated). A ring already 90% built in 2017 uses the 1-3 km ring; if both are, the factor is
    `built_out`: not scored, and it does not withhold the decision.
  - **Decision rules** (`ml-models/scoring_engine/_verdict.py`):
    - AVOID only on hard evidence: proven legal risk (unchanged), or a red flag from the plot's history:
      modelled river flooding over 25% of the plot at 1-in-100 or more often; open water seen on the plot in
      at least 10% of Landsat passes 1984-2021 on average (a likely tank or lake bed); or the plot mapped as
      water / flooded vegetation in any year 2017-2023.
    - Otherwise BUY at a composite of 75 or more, else WAIT. The composite is shared over the scored factors.
      The WAIT summary names the weakest factor.
    - Unscored legal safety no longer withholds the decision. It becomes the "before you pay" checklist
      (`verdict.pre_purchase_checks`); title is still never verified. A change in the plot's own class
      between 2017 and 2023 is added there too.
    - An unscored *location* factor (area growth, accessibility) still withholds the decision.
  - **Report:** the badge asks "Buy now or wait?". A new section under it shows red flags, the built-up
    chart for both rings, the plot's own class each year, and the checklist. Old reports say to analyse the
    boundary again. The land-cover row is in the evidence ledger (Satellite tab) and is cited in the summary.
  - **Schema:** `land_cover_history`, `verdict.red_flags`, `verdict.pre_purchase_checks`, factor status
    `built_out`.
  - **Bugs found and fixed in passing:** at 375 px the report scrolled sideways (620 px): the accessibility
    table widened its grid track. The ETL tests reached the network for the new collector; they now stub it.
- **Verification (2026-10-20, audit copy `.local-ui-check/audit/backend-audit-2026-10-20.sqlite3`):**
  - **Land cover, cold reads:** 2.2-3.8 s per parcel. Rural Tiruvannamalai fields +0.11 points a year;
    Kelambakkam (OMR) +1.81; Oragadam +1.03; T Nagar 100% built (built out); rural Kadapa 0.
  - **Real analyses through the API, homebuyer lens:**
    - VIT acceptance plot: BUY, composite 94. Accessibility 92; area growth 96 (63% to 73% built within 1 km,
      2017-2023). Four title checks listed.
    - Kelambakkam: AVOID. Area growth 90, but modelled river flooding covers 91% of the plot at 1-in-10.
    - Rural Tiruvannamalai: WAIT, composite 19 (growth 6, accessibility 31).
  - **Timings:** a repeat analysis took 2.5 s. Evaluation p50 0.27 s (n=12), the same as J-55's 0.26 s.
    Requests to `localhost` cost about 2 s each on this machine (IPv6 first) against 18 ms for `127.0.0.1`.
    The services already call each other on 127.0.0.1, and the first 2.4 s figure came from the test script.
  - **Browser:** the VIT, Kelambakkam and an old report at desktop and 375 px. No console errors, no sideways
    scroll after the fix.
  - **Tests:** ml-models 59, data-pipeline 80, backend-api 11, valuation 52. Integration: 17 passed, 1
    skipped. The integration run first caught `built_out` missing from the schema enum (central Chennai
    parcels); fixed, with a schema-validated regression test. Frontend type-check and build pass.
  - **Your store:** byte-identical before and after (93 snapshots, 58 evaluations, 9 documents); a normal
    start serves it.
- **Limitations:**
  - Every threshold (2 points a year, 75, 25%, 10%, 90%) is a rule, not calibrated against prices or sales.
  - Built-up land is a proxy for demand. It does not show prices, approvals or planned infrastructure, and the
    maps stop at 2023.
  - The classification is modelled; small plots (a few hundred 10 m pixels) inherit its errors.
  - The 58 saved evaluations keep their old verdicts. A re-evaluation without re-analysis stays "no decision
    yet", because those snapshots have no area history.
- **Status:** fixed and verified. This supersedes J-53's position that growth stays unscored: growth is now
  scored from the area's observed development, not from the plot's NDVI/NDBI. The thresholds are still open
  (checklist section 2).

## J-57 Completion pass: findings with next steps, failure messages, upload validation

- **Date / problem:** 2026-10-25, before the demo deadline.
  - The answer and its reasons were spread over many sections. There was no single place listing each check with its
    status, source, date and next step.
  - With a service stopped, the report said "Evaluation timed out: " (504) with an empty reason. On Windows a refused
    loopback connection arrives as a connect timeout after ~2 s.
  - After a failed scenario re-run, Apply was greyed out (the settings were saved before the request succeeded), and
    a failed "Re-evaluate with current methods" showed nothing (its error went to the closed scenario drawer).
  - The upload endpoint stored empty files and files for parcels that do not exist.
- **Changes:**
  - **Findings** (`ml-models/findings.py`, `verdict.findings` in the schema): one row each for title, RERA, river
    flooding, water on the plot 1984-2021, rainfall/coastal flooding, area development, the plot itself, and road and
    school access. Each row has status `red_flag | caution | ok | unknown` and basis
    `measured | modelled | user_provided | not_verified | unavailable`, plus source, date and next step. Rows are
    sorted red flags first. Missing evidence is `unknown`, never `ok`. The report adds the existing price result as
    a final row (shown, not computed). Re-evaluate shows on any evaluation without findings.
  - **Errors** (`backend-api/routers/parcels.py`): a connect timeout goes to the existing unreachable-service message,
    which now names the service and address and says to run `terrascope.cmd start` (502). Real read timeouts keep 504.
  - **Report:** settings change only after a successful re-run; a failed banner re-evaluation shows an alert.
  - **Uploads:** an empty file returns 400; an unknown parcel returns 404.
  - **README:** a five-minute demo guide.
- **Verification (2026-10-25, audit copy `backend-audit-2026-10-25.sqlite3`):**
  - **API:** 30/30 checks of valid, invalid and missing inputs on every public endpoint (`scratch` script, not in the
    repo). This covered bad polygons, reversed dates, outside India, bad preferences, unknown parcels, empty and wrong
    file types, and the valuation refusal.
  - **Browser, full workflow:** search "Katpadi", draw a 16 ha plot, analyse (about 20 s), open the report: WAIT,
    steady development (2% to 9% built within 1 km), school 4.6 km. Re-evaluate added the findings: "No red flags,
    1 to check, 4 not verifiable here". Desktop and 375 px, no sideways scroll; no console errors in a fresh tab (the
    `createRoot` warnings seen earlier came from Vite hot reloads).
  - **Service down:** with ml-models stopped, the API returned the new 502 message, the scenario drawer showed it,
    Apply stayed enabled, and after restarting ml-models the same Apply succeeded (road limit 1,500 m applied).
  - **Tests:** ml-models 60, data-pipeline 80, backend-api 13, valuation 52; integration 17 passed, 1 skipped (needs real
    price data); frontend type-check and build pass.
- **Limitations:** saved reports cannot be deleted from the app. The findings' assessment cut-offs (access 60/100,
  growth 50/100) are rules, not calibrated.
- **Status:** fixed and verified.

## J-58 Land prices removed from this version

- **Date / decision:** 2026-10-25, the user's decision. No reliable, permitted, verified price data exists (J-52), so
  the report and the demo show no land price, range, placeholder or "No price estimate" message.
- **Changes:**
  - **Frontend:** removed the price section, the price row in "What we found", the "Price data" import page and its
    start-page button, the workspace property box (land use, price basis, plot area: used only for prices), the
    valuation call in the analysis flow and on reopening a report, and their styles and API client calls.
  - **Backend:** the `/api/v1/valuation/*` routes are no longer served (`routers/valuation_routes.py` deleted).
  - **Findings:** area-development next steps no longer mention prices.
  - **Config and tooling:** `VALUATION_OBSERVATIONS_PATH` removed from `.env.example` and `docker-compose.yml`;
    `scripts/benchmark.py` no longer times a valuation request.
  - **Tests:** the six price integration tests are gone (one was always skipped); a new test checks the price
    endpoints return 404. The file is renamed `test_evidence_and_reports.py`.
  - **Docs:** README ("Land prices: not in this version"), the demo guide and the checklist. The `valuation/` package
    and `docs/SETUP_VALUATION.md` stay, marked unused, for a later version.
  - **Decision logic:** unchanged. Price never fed BUY / WAIT / AVOID (it was a separate service); nothing in
    `ml-models/scoring_engine` referenced it.
- **Verification (2026-10-25):** ml-models 60, data-pipeline 80, backend-api 13, valuation (unused module) 52;
  integration 13 passed (was 17 + 1 skipped: minus 6 price tests, plus the 404 guard). Frontend type-check and build
  pass. Browser, read-only views on the user's store: start page, a saved report and the workspace show no price
  wording (whole-word check) and no console errors.
- **Status:** done and verified.

## J-59 Area development read "88% to 89% (-0.0 points a year)"; dataset audit

- **Date / problem:** 2026-10-25. A Vijayawada report (VJ Polytechnic, Krishna district) said built-up land within 1 km
  went from 88% in 2017 to 89% in 2023 at "-0.0 points a year", under "Little or no development". It also gave no
  decision with only "no infrastructure was retrieved".
- **Root cause (confirmed from the stored values):**
  - Shares were correct (0.8822 to 0.8858, i.e. 88.2% to 88.6%). Whole-percent rounding printed them as 88% and 89%.
  - The trend is a least-squares fit across all seven years. The series dipped in 2020-2022 (0.8803, 0.8782, 0.8783), so
    the fit was ~-3e-15, float noise. `round(..., 2)` kept it as -0.0, which printed as "-0.0". Any slope between -0.05
    and 0 would also have printed "-0.0".
  - "Little or no development" described an 88%-built ring as if it were empty.
  - No decision was correct: Andhra Pradesh has no regional OpenStreetMap data, so accessibility was unscored. The
    message did not say that, although the snapshot held the exact install command.
- **Changes:**
  - `connectors/land_cover_history.py`: the stored slope adds `+ 0.0`, so it can never be -0.0.
  - `scoring_engine/_assessment.py`: one formatter (`points_a_year`) rounds before formatting. Shares print to one
    decimal. The text names the all-years trend separately from the first and last year. A ring at least 75% built
    reads "Little new building in an already dense area" (wording only: the score rule is unchanged). Missing regional
    data names the state and the exact `terrascope.cmd fetch-data <region>` command.
  - `findings.py`: the dense-area next step and the exact install command.
  - `etl_pipeline.py`: the land-cover ledger line uses the same format for new snapshots. Existing snapshots keep their
    saved line until the boundary is analysed again (snapshots are immutable).
  - `docs/DATASETS.md`: the dataset audit, gaps, download plan with measured sizes, and researched sources.
- **Verification (2026-10-25):** the Vijayawada snapshot re-evaluated on an audit copy now reads "88.2% in 2017 and 88.6%
  in 2023; the trend across all 7 years is 0.0 points a year" under "Little new building in an already dense area", and
  "Install it with terrascope.cmd fetch-data andhra-pradesh". Regression tests for the -0.0 slope (connector and
  assessment) and the install command. ml-models 62, data-pipeline 81, backend-api 13; integration 13 passed.
  Dry run of `fetch-data andhra-pradesh` (metadata only): OSM and surface-water tiles reused, 37 DEM tiles = 1.41 GB.
- **Open:** a flat trend in a dense area still scores 0 for area growth; whether an established area should count
  against BUY is a product decision, not a bug. Nothing was downloaded; Andhra Pradesh needs the user's go-ahead.
- **Status:** fixed and verified.

## J-60 Decision clarity, level vs rate, and Andhra Pradesh regional data

- **Date / problem:** 2026-10-25.
  - The decision was not stated in buyer words (AVOID, INSUFFICIENT EVIDENCE), and the summary opened with a composite
    figure.
  - An already-dense area with little new building scored 0 for area growth, as if it were empty land. Level of
    development and rate of new development were conflated.
  - Andhra Pradesh had no regional data, so the Vijayawada plot had no decision.
- **Changes:**
  - **Level vs rate** (`_assessment.py`): a 1 km ring at least 75% built gaining under 0.5 points a year is an
    *established* area. It is described, not scored for or against, and does not block. A dense area still building
    fast is scored as before. Both thresholds are provisional and disclosed. This was not tuned toward BUY.
  - **Wording** (`_verdict.py`, report): BUY / WAIT / WALK AWAY / INSUFFICIENT DATA (stored codes unchanged). The
    summary starts with a plain sentence built from the findings, then the development figures, the road and school
    distances, what holds a WAIT back, the composite, and the unverified legal checks.
  - **Report:** the explanation first; strongest positives and negatives and an evidence-completeness count (from the
    findings); a nearby-facilities table (road, school, hospital, bus, rail) with distances, names, source and data
    date. Colleges, markets and shops are stated as not collected.
  - **`docs/DECISION_RULES.md`:** every rule with its evidence, reason, effect, missing-evidence behaviour and
    validation status.
  - **Andhra Pradesh:** `terrascope.cmd fetch-data andhra-pradesh` reused the OSM extract and the surface-water tiles.
    It downloaded the DEM tiles: the build's own list needed 54 (11 already on disk); 11 were downloaded by the build and 32 by a parallel helper
    using the same source and file names, with sizes checked. The store took 329 s to build (204 MB). Throughput was
    about 0.1-0.35 MB/s per connection; one HTTP 504 on signing was retried.
- **Verification (2026-10-25, audit copy `backend-audit-2026-10-25c.sqlite3`):**
  - **Vijayawada,** the exact saved boundary re-analysed in 8 s with regional data `andhra-pradesh`. Road 1 m, school
    326 m, hospital 309 m, bus 408 m, rail 2.1 km, canal 1.4 km, elevation +7.1 m above water, no surface water, no
    modelled river flooding. Land cover was 88.2% to 88.6% (all 7 years); the area is established.
  - **Decision: BUY, composite 96.** It rests on accessibility alone, because the established area is not scored and
    legal and flood have no score. Title, RERA, rainfall waterlogging and coastal flooding remain Unknown.
  - **Tamil Nadu:** VIT BUY 94 (fast growth); Kelambakkam WALK AWAY (91% flooded at 1-in-10, despite growth 90).
  - **Tests:** ml-models 65, data-pipeline 81, backend-api 13, valuation 52, integration 13; frontend type-check and
    build pass.
  - **Browser:** the new report has the badge, explanation, highlights, five facility distances and no "-0.0"; no
    console errors in a fresh tab; no sideways scroll at 375 px.
  - **User store:** byte-identical before and after (`8e84f611…`); backups intact.
- **Open:** a BUY can rest on a single scored factor when the others are established or unscored, as for Vijayawada.
  Whether a BUY should need at least two scored location factors or full flood coverage is a product decision, not
  made here.
- **Status:** fixed and verified.

## J-61 BUY needs due diligence; plain-language charts; satellite basemap; local news; claims; measured speed-ups

- **Date / problem:** 2026-10-26.
  - A strong location gave BUY although title, encumbrance, zoning and approvals were unverified (Vijayawada BUY 96).
  - An unmapped school scored 0, as if confirmed absent (Senjeri: accessibility 32).
  - The charts assumed the reader knew NDVI and NDBI.
  - There was no satellite view, no local news, and no way to record a resident's information.
  - The report list parsed every snapshot (N+1), and the first analysis after a restart waited 5 s for the India boundary.
- **Changes:**
  - **Decision** (`_verdict.py`): BUY only with location score ≥ 75 AND verified legal checks (matched land records).
    Otherwise a strong location is WAIT, naming the pending checks. Every answer lists `verdict.would_change`. The
    score is labelled "location score, rule-based, not a probability". Past development is labelled 2017-2023 history.
  - **Unmapped is not absent** (`scoring.py`, `findings.py`): a road or school OpenStreetMap has not mapped is left out
    of the score; the report says "not confirmed absent" and asks for a local check. If nothing is mapped,
    accessibility is unknown and the answer is INSUFFICIENT DATA.
  - **Charts** (`Report.tsx`): titles, plain subtitles, axis labels and units, a one-sentence finding (inconclusive
    spelled out), "What does this graph mean?" explainers (NDVI, NDBI, land cover, change detection, cloud, season,
    resolution, mixed pixels), and a too-few-images note.
  - **Satellite basemap** (`ParcelWorkspace.tsx`): "Map" or "Satellite (2023)" from EOxCloudless 2023 (Sentinel-2
    composite, 10 m, CC BY-NC-SA 4.0), with attribution. A note says it is 2023 imagery, not today's and not analysis
    data, and failed tiles show a message with no substitute imagery. Esri World Imagery was not used: its licence
    terms for this use are unclear.
  - **Local news** (`backend-api/routers/area_intel.py`): a provider interface with GDELT DOC 2.0 (free, no key) as
    the only provider.
    - Three searches (hazards, legal/planning, development), each requiring the locality (with spelling variants) and
      the district.
    - Duplicates and syndicated copies are merged. Each event is labelled official source, 2+ outlets or single
      report, with speculative and older-than-2-years flags.
    - Searches are spaced at 6 s, with a 15 s back-off after HTTP 429. A per-locality lock means concurrent requests
      search once.
    - Results are cached 24 h with their retrieval time; failures are never cached. News never changes the decision.
  - **Development claims:** a per-parcel table and form (claim, type, source, distance, expected date as claimed,
    evidence link, date checked). Claims stay "not verified", with an effect sentence that assumes nothing is
    completed.
  - **Performance:** the report list is one SQL query reading only the fields shown, with indexes on per-parcel
    lookups. The India state polygons get a WKB sidecar tied to the source's size and modification time, preloaded in
    the background at start-up. Geocoding is kept on disk (30 days, successes only).
- **Measurements (same machine):**
  - Report list (95 reports): 149 ms → 24 ms median.
  - India boundary load: 4.8 s → 0.31 s.
  - First analysis after a restart: 8.8 s → 2.4 s. A warm re-analysis is 1.4 s.
  - Report reopen: 12-22 ms (unchanged).
- **Verification (2026-10-26, audit copy `backend-audit-2026-10-26.sqlite3`):**
  - Senjeri re-evaluated: WAIT, location score 90 ("location strong, legal checks pending"; the school is unmapped,
    not absent; satellite signal inconclusive, explained).
  - Browser: decision, would-change list, both charts with titles, axes, findings and explainers, the score label,
    news (no indexed results, cached) and a recorded resident claim. The satellite basemap loads 2023 tiles with the
    drawn boundary kept and the attribution shown. No sideways page scroll at 375 px.
  - **Live news:** one successful search (Senjeri + Coimbatore: no indexed results). All other live attempts returned
    GDELT HTTP 429 and were shown as "unavailable". The results path is verified with a fake provider only.
  - **Tests:** ml-models 67, data-pipeline 84, backend-api 25, valuation 52, integration 13; frontend type-check and
    build pass. There is no frontend unit-test runner (none added); tile failure was checked by code only.
  - **User store:** byte-identical before the normal start. A new backup `backup-2026-10-26` was taken first; the
    start added the empty `development_claims` and `news_cache` tables and four indexes; all existing rows are
    identical to the backup.
- **Limits:**
  - BUY is unreachable until a land-records source exists (by design).
  - GDELT is headline-level, rate-limited and has no stated licence page; conflicting reports cannot be detected from
    headlines.
  - The 2023 basemap is 10 m; there is no historical imagery picker.
  - The parcel-result cache is one JSON file (fine at 48 entries, linear in size).
- **Status:** fixed and verified, except a live news "results" case (blocked by provider rate limiting).

## J-62 Review readiness: legal gate, stale-evaluation banner, news time budget, demo rehearsal

- **Date / problem (2026-10-26):**
  - A decision-engine scenario check found that a matched record showing an unclear title and an encumbrance summed
    to exactly the 70-point limit and gave WAIT. It also found that any matched record (even a defective one) counted
    as completed due diligence for BUY. Zoning and approvals could not be represented at all.
  - Saved evaluations made under older rules (no `would_change`) showed no re-evaluate banner.
  - A rate-limited news search kept the buyer waiting 189 s before "unavailable".
  - A high location score could sit next to WAIT or WALK AWAY with no explanation.
- **Changes:**
  - `_verdict.py`: BUY only when title clear, no encumbrance, zoning verified and approvals verified are all positively
    recorded; a missing value is pending. An unclear title or an encumbrance is WALK AWAY. WAIT names the specific
    pending checks.
  - Schema: `land_records.zoning_verified` and `approvals_verified` (additive, null by default).
  - Report:
    - a note under the location score ("describes the location only; never overrides red flags or pending legal
      checks");
    - the re-evaluate banner on any evaluation without `would_change`;
    - "none mapped" explained as not confirmed absence;
    - the news failure text says "temporarily unavailable".
  - Satellite note: "It cannot show ownership, legal access, title, zoning or safety."
  - `area_intel.py`: a 45 s budget for the whole news search; waits, timeouts and the 429 back-off are clipped to it.
  - `DATASETS.md`: academic vs commercial licensing, and licensed alternatives.
- **Verification (2026-10-26):**
  - **Decision scenarios:** 8/8 through the full evaluation path on the VIT fixture: legal unknown → WAIT; all four
    verified → BUY; defective title → WALK AWAY; flood red flag → WALK AWAY; no infrastructure → INSUFFICIENT DATA;
    unmapped school left out; weak growth → WAIT naming the cause; no area history → INSUFFICIENT DATA. No price,
    appreciation, guarantee or clearance wording in any output.
  - **Tests:** ml-models 68, data-pipeline 84, backend-api 26, valuation 52, integration 13; frontend type-check and
    production build pass.
  - **Browser, disposable copy:** Senjeri re-evaluated (WAIT 90, legal pending). Both explainers cover every required
    concept. Readable at 1366x768. Satellite toggle: 12 EOX tiles; boundary kept; attribution and date shown; forced
    tile failures showed the fallback note and the map kept working; switching back to Map restored OSM tiles.
  - **Fresh start on the user's store** with `terrascope.cmd start`: four services healthy; the saved Senjeri report
    opened from the list with the stale-evaluation banner; news reported "unavailable" (GDELT 429) within about 25 s;
    a browser refresh reopened the same snapshot; the satellite view loaded over Senjeri; no console errors; service
    logs clean.
  - **User store:** byte-identical to the pre-review baseline (`4590829b…`, 96/63/9) after the rehearsal; a verified
    backup `backup-2026-10-26-review` was taken first.
- **Limits:** no land-records, RERA, rainfall-flood or coastal source; GDELT is rate-limited from this network, so the
  news results path is demonstrated with recorded test fixtures only; the basemaps are not licensed for commercial use.
- **Status:** fixed and verified.

## J-63 Satellite blur, news timeline, legal-check workflow, licensing evidence

- **Date / problem (2026-10-26):**
  - The satellite view looked blurred when zoomed in.
  - News covered only 3 years.
  - There was no place to record official legal checks.
  - Map licensing was asserted rather than verified.
- **Diagnosis:**
  - EOX tiles above zoom 14 add 1-3 grey levels of detail versus 8 at zoom 14; Esri adds about 11 at every level to
    18. The blur is the 10 m source.
  - GDELT's DOC API searches from 2017-01-01 (verified with a 2018 query; its blog posts disagree).
- **Changes:**
  - Satellite `maxNativeZoom` 14, plus a note when zoomed past it.
  - News timeline from 2017 (at most 10 years): grouped by year, with the headline's reported project status, evidence
    type, and a flag when the headline does not name the locality. 250 records per topic, with a notice when that limit
    is reached. A 2-minute pause after a GDELT 429.
  - Legal checks: Tamil Nadu state guide, append-only manual records. A recorded problem gives WALK AWAY and a red-flag
    finding; a recorded confirmation never gives BUY. Schema field `user_legal_checks`.
  - Local date for check dates; the old UTC default showed yesterday in the Indian morning.
  - Docs: `LEGAL_VERIFICATION.md`; measured sharpness and verified licence terms in `DATASETS.md`.
- **Verification:**
  - **Tests:** ml-models 70, backend-api 28.
  - **Browser, user's store (view only):** at zoom 16 only zoom-14 EOX tiles load and the note shows.
  - **Browser, disposable copy:** recorded an EC and a title check → WAIT naming both as "recorded by you". Recorded a
    zoning problem → WALK AWAY, no score, "1 red flag". RERA "not applicable" is offered only for RERA. 4 rows stored,
    one per action.
  - **Two defects caught by the browser run and fixed:**
    - the schema rejected `user_legal_checks`;
    - the findings disagreed with WALK AWAY.
  - **Live GDELT:** rate-limited (HTTP 429) for both attempts. The timeline is verified with test fixtures only.
- **Limits:**
  - No automated land-record, EC, zoning or approval source for any state.
  - Rainfall and coastal flooding not assessed.
  - Event dates and distances are not derivable from headlines.
- **Status:** fixed and verified, except the live news results path (blocked by the rate limit).

## J-64 Government, public-facility and restricted-land detection

- **Date / problem (2026-10-26):** nothing checked whether a plot lies on a court, stadium, railway, defence area,
  water body or other public land. A buyer could see a strong score for land that cannot lawfully be sold.
- **Changes:**
  - **Map store:** a public-facility store per region, built from the extract on disk (no download). Tamil Nadu: 5.0 MB
    in 86 s; Andhra Pradesh: 3.1 MB in 97 s. `osm.sqlite` is untouched.
  - **Contact measurement:** overlap vs touch vs nearby, measured on the parcel polygon with a ±15 m uncertainty.
    Facility type is kept apart from any operator/ownership tag.
  - **Official checks:** a `government_land` record type (outcome, source, survey number, date), kept per source so
    conflicts stay visible. Tamil Nadu guide: the e-Services poramboke verification, A-register, FMB sketch and
    taluk office.
  - **Decision engine:** the government-land status is decided before scores (WALK AWAY / hold at WAIT / no hold), and
    a "Government and restricted land" finding is added.
  - **Report and map:** a new report section (mapped facilities, ownership signal, nearby, data date, limits); overlap
    polygons and markers in the workspace Layers.
  - **Schema:** `public_land`, `user_government_land`, `verdict.government_land`, and a `mapped` basis.
- **Verification:**
  - **Unit tests, synthetic geometry only:** 7 connector tests and 7 decision tests covering the 9 required scenarios,
    plus a pipeline test with schema validation and a backend test.
  - **Real map data (read-only):** test boundaries inside the Madurai Bench of the Madras High Court and inside MA
    Chidambaram Stadium each report an overlap with ownership unknown. The saved Senjeri boundary has no mapped
    facility within 2 km.
  - **End to end, disposable copy:** a test boundary over the stadium gave WAIT with the warning first.
    - Adding a TEST "private per record" kept WAIT with a boundary-check requirement.
    - Adding a TEST A-register "non-transferable" from a second source gave "Official records conflict", WAIT.
  - **Defect caught and fixed:** the schema rejected the new `mapped` basis.
  - The user store is row-identical to the backup afterwards.
- **Limits:**
  - No authoritative public-land geometry for any state.
  - Official checks are manual.
  - OSM coverage is incomplete and ±15 m.
  - Saved reports predate the check until analysed again.
  - Stores exist only for Tamil Nadu and Andhra Pradesh.
- **Status:** fixed and verified (mapping and decision rules); official verification remains manual.

## J-65 All-India data: verified extract, nationwide non-road store, per-layer status, Bhuvan decision

- **Date / problem (2026-10-26):** only Tamil Nadu, Puducherry and Andhra Pradesh had local map data. In the other 33
  regions every map layer was missing, and nothing distinguished "not installed" from "nothing mapped".
- **Constraints measured:** C: is the only drive and had 5.1 GB free; RAM was 15.4 GB with about 2 GB free. A
  nationwide store with roads would be about 3 GB plus a temporary copy, so it does not fit.
- **Changes:**
  - **Source:** downloaded `india-261025.osm.pbf`, 1,711,981,786 bytes. The MD5 matches Geofabrik's published file
    and the header is valid (data to 2026-10-25 21:21 UTC). The original is kept unchanged.
  - **Memory-safe build** (`fetch_data.py --national`): pyosmium `BackReferenceWriter` copies only the non-road
    features and their referenced nodes into a derived file. The existing builders then made `regions/india/osm.sqlite`
    (523 MB) and `public_land.sqlite` (69 MB). The derived file was removed. Build time about 23 min; memory stayed
    within the allocated swap file.
  - **Stores record their layers** (`store_meta.layers`); `LocalOSM.has_layer`. The ETL emits
    `infrastructure.layer_status`. A road that is not installed reads "not installed (unknown)" in the evidence, the
    facilities table and the scoring. Accessibility becomes unavailable (never scored from schools alone), so the
    decision is INSUFFICIENT DATA.
  - **Region choice:** the smallest covering store wins, so a state store with roads beats the all-India store. One
    store per parcel, so regional and national features are never combined or double-counted.
  - **Registry** (`dataset_registry.py`): tests a sample point in each of the 36 regions and writes
    `docs/DATASET_REGISTRY.md` and `docs/datasets/registry.json`.
  - **Bhuvan:** the live terms make content "for viewing purposes only"; reuse through other means or derivative works
    needs written authorization from DOS/ISRO/NRSC. Only metadata (GetCapabilities) was requested. Nothing is
    integrated; candidate layers are documented in `DATASETS.md`.
- **Verification:**
  - Both stores pass `integrity_check`; feature counts match their indexes; extent is 68.0-97.6°E, 6.8-36.0°N.
    Features fall inside every one of the 36 regions (`docs/datasets/national_store_counts.json`).
  - Registry: all 36 regions resolve to the correct state. Schools/hospitals/transport, water and public facilities
    are installed for all 36; roads for TN, PY and AP only.
  - **End to end, disposable copy:** test boundaries in Patna, Pune, Guwahati, Delhi, Kochi and Leh read the all-India
    store.
    - Roads show "not installed" → INSUFFICIENT DATA; schools, hospitals, water and public facilities are real.
    - Guwahati: WALK AWAY from the JRC 1-in-50-year river flood, with source and date.
    - Coimbatore read the Tamil Nadu store with roads → WAIT.
    - All 96 pre-existing reports opened via the API with no failures.
  - **Defects caught and fixed:**
    - the schema rejected `layer_status` (every new analysis failed);
    - the national stores had no data date.
  - The user store is row-identical to the new backup `backup-2026-10-26-national`.
- **Limits:**
  - Roads outside TN/PY/AP need about 3 GB more disk.
  - Bhuvan needs written permission.
  - OSM completeness varies widely by state (Kerala has 15,109 schools mapped, Mizoram 8).
- **Status:** fixed and verified, except nationwide roads (blocked by disk space).

## J-66 Conditional BUY with a development outlook and a disclaimer (2026-10-27)

- **Decision (user):** a strong, developing location should be BUY, with a clear disclaimer.
- **Changes:**
  - **Rule:** location score ≥ 75 → BUY; otherwise WAIT. Unless matched records verify the four legal checks, the
    BUY reads "Buy only after the legal checks: …", and "what would change it" says a defect found in them means WALK
    AWAY.
  - **Unchanged:** restricted land, legal defects, flood red flags and potential public land still decide first.
  - **`_outlook.py`:** a straight-line fit of the seven yearly built-up shares within 1 km, projected to 2026 and 2030
    with a 95 % prediction interval (Student t). Saturated areas (≥ 85 % built) are "built out". It projects building,
    never prices. Shown in the panel as "20% → ~32% (22%–41%)".
  - A disclaimer on every report: an estimate, not perfect, not legal or financial advice.
- **Verification:**
  - Tests updated to the new rule: ml-models 88, backend-api 30, data-pipeline 96, valuation 52, integration 13 passed.
  - Disposable copy: Senjeri → BUY (score 90, 2030 projection 32 %, range 22-41 %). Mamillapalli → WAIT (stadium
    overlap).
- **Limits:** a linear trend cannot foresee new projects or policy; the range only reflects past scatter.
