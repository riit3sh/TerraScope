# TerraScope handoff (2026-10-27)

You are taking over unfinished work in `C:\Users\nagir\TerraScope-team`. Read this whole file before you change anything.

## Rules from the owner (non-negotiable)

- **Preserve the real data.** Never delete, reset, reseed or overwrite the real reports database, existing reports,
  evaluations, documents, `.env`, secrets, backups or user files. Run tests, re-analysis and anything that writes reports
  against a **disposable copy**: set `BACKEND_STORE_PATH` to a copied store before starting the services
  (`powershell -NoProfile -File scripts/terrascope.ps1 start`). Viewing reports in the browser is fine.
- **No fake data.** Do not fabricate data, benchmark numbers or test cases, and never present missing data as safe.
  "Unknown" must stay "unknown".
- **Commits:** do not commit, push, merge or force-push until the owner has seen the final diff and said yes. Never
  merge PR #3 or any PR yourself. Never commit `.env`, databases, `data-cache/`, caches or large extracts.
- **Services:** stop them only with `terrascope.cmd stop`. Do not kill unrelated processes or free ports.
- **No scraping or captcha bypass.** No contacting organisations, creating accounts or spending money without approval.
- **Disk:** C: is about 98 % full. Do not delete large files without approval.
- Use the project venv: `.venv\Scripts\python`. Set `PYTHONIOENCODING=utf-8`, and use `127.0.0.1`, not `localhost`,
  in Python scripts.

## Git state

- **Branch `sai/report-redesign`:**
  - local merge commit `a660499` brings Ritesh's 7 commits from `main` (up to `9418647`) onto the RERA commit
    `f773780`;
  - not pushed;
  - all the work below is **uncommitted** (13 files).
- **Backups** of the uncommitted work (delete only after it is safely committed):
  - `git stash@{0}`;
  - the patch `C:\Users\nagir\AppData\Local\Temp\claude\C--Users-nagir-diskframe\8189942a-c1f2-4baf-806e-5d282a4eae67\scratchpad\redesign-roads-wip.patch`.
- **PR #3** (`sai/rera-workflow`, RERA workflow): open. Do not merge it.
- **Plan for publishing:**
  1. review `git diff`;
  2. show it to the owner;
  3. on approval, commit (message ending `Co-Authored-By` as the owner prefers);
  4. push `sai/report-redesign`;
  5. open a PR to `main`.

## What is done (uncommitted, tested)

1. **Report redesign:**
   - `frontend/src/pages/ReportSummary.tsx` (new): `SummaryCard`, `plainAssessment`, `keyFindings`, `ParcelThumb`,
     `PlotIds`;
   - `frontend/src/pages/Report.tsx`: the order is the summary card, then the "Before you pay" plain-English legal
     checklist, then the disclaimer, then "More detail" collapsible sections;
   - `frontend/src/styles.css`;
   - `KpiStrip.tsx` deleted.
   - A conditional BUY shows as "Buy after checks" (amber). Plain "Buy" appears only when all four legal checks are
     verified from records.
   - Printing opens every collapsed section.
2. **Ritesh's changes are kept:**
   - restricted reports show their evidence, labelled "Verify restriction";
   - findings show only evidence-backed rows;
   - local news and future-development claims are removed from the report.
3. **"Insufficient data" is no longer a verdict:**
   - `ml-models/scoring_engine/_verdict.py` returns `WAIT`, and names what could not be measured;
   - old saved `INSUFFICIENT_EVIDENCE` reports display as Wait;
   - the tests and `README.md` / `docs/DECISION_RULES.md` are updated.
4. **All-India roads:**
   - `data-pipeline/fetch_data.py --national-roads` builds `data-cache/regions/india/roads.sqlite` from
     `downloads/india-*.osm.pbf`;
   - `etl_pipeline._local_amenities` uses it when a state has no road store of its own;
   - a test was added in `connectors/test_local_osm.py`.
5. **Report header:** a small OpenStreetMap thumbnail of the drawn boundary, the centre coordinates, and the survey
   number when the buyer entered it. Otherwise it says "Not entered. TerraScope cannot look it up".

Last full test run, all green:

| Suite | Passed |
|---|---|
| ml-models | 92 |
| backend-api | 33 |
| data-pipeline | 99 |
| valuation | 52 |
| integration | 13 |

The frontend `npx tsc --noEmit`, `npm run build` and `node checks/area.check.ts` also pass.

## Still to do, in order

1. **Verify the all-India roads in the app.** The build is finished.
   - **The store:** `data-cache/regions/india/roads.sqlite`, 3.13 GB, 8,914,911 vehicular roads. The source is the
     Geofabrik India extract with data as of 2026-10-25.
   - **The manifest:** `manifest.json` has a `roads` entry. The old manifest is kept as
     `manifest.json.bak-before-roads`.
   - **Temporary files:** removed.
   - **Read-only checks:** nearest road 6 m in Erragadda (Hyderabad), 41 m in Delhi and 8 m in Patna.
   - **Still to do:**
     1. restart the services so the new store is read (`terrascope.cmd stop`, then start);
     2. on a **copy** of the reports store, re-analyse a Telangana plot (Erragadda, parcel
        `e0b98892-1309-4bcb-9850-a3a0344daa97`) and a Delhi plot;
     3. confirm that road distance and accessibility are measured, and that the answer is BUY / WAIT / WALK AWAY.
2. **Update the docs for roads.** Update `docs/DATASETS.md` (the "All-India store, no roads" row and the "Roads" gap row)
   and the README "Known limitations" roads bullet with the real size and counts from `manifest.json`. Add a
   milestone entry to `docs/PROJECT_JOURNEY.md` (the owner wants every milestone logged there).
3. **Add a "Not checked by TerraScope" list to every report.** Put it in a "More detail" section or under the key
   findings, so nothing is silently missing. Name the gaps:
   - earthquake zone;
   - landslide;
   - high-tension power lines and pipelines;
   - airport height limits;
   - coastal regulation zone (CRZ) and eco-sensitive zones;
   - zoning / master plan;
   - rainwater flooding;
   - monuments and heritage sites (until implemented);
   - price.

   Keep it honest: "not checked", never "safe".
4. **Run every suite again**, then check in the browser:
   - a BUY-with-incomplete-legal report (Kadapa `2fa1cbba-5d46-4a67-ae57-859ce3d52ef4`);
   - a potential restriction (`7396823f-a47c-4744-9dab-8906497cdf33`);
   - a restricted one (`173e1fa4-a3f0-481f-a482-2c9990ea8807`);
   - an older saved report (`fbbbc3e7-8173-4e0b-967e-b64adae15246`);
   - a mobile width (375 px): no sideways scroll;
   - printing.
5. **Review the full diff, show it to the owner, and commit and push only after approval.**

Then report to the owner what changed, which tests passed, and what still needs improvement.

## Known gaps (tell the owner; do not fake them away)

- **Legal checks:** title, encumbrance (EC), zoning and approvals are manual in every state, because no state offers a
  permitted API.
- **Survey numbers:** there is no cadastral map, so survey numbers cannot be looked up, and the drawn plot cannot be
  matched to the patta.
- **Monuments and heritage sites:** not implemented. A plan awaits the owner's approval in a separate session.
- **Flooding:** only river flooding is modelled. Rainwater and coastal flooding are not assessed.
- **Distances** are straight-line, not routed, and do not prove legal road access.
- **OpenStreetMap completeness** varies by state.
- **Prices:** none, because no permitted data exists.
- **Land-cover history** ends in 2023.
- **Language:** the report is English-only.
- **Tests:** there are no automated frontend tests for the report page.
- **Deployment:** local-only on Windows, with no login or multiple users.
