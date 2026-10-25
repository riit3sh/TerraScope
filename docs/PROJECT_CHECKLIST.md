# TerraScope project checklist

The single current progress checklist. Last updated 2026-10-25 (area-development display fix and dataset audit, J-59; land prices removed, J-58; completion pass, J-57; buy/wait decision, J-56).

Rules: an item is "verified" only when a recorded check exercised the real behaviour (real services, real
data, or the browser), not because code exists, a mocked test passes or a page loads. "Implemented" without
"verified with real data" means exactly that. History and causes are in [PROJECT_JOURNEY.md](PROJECT_JOURNEY.md)
(J-numbers below).

Acceptance case for 2026-10-12: the VIT Vellore report, snapshot `568d1f42` (2.75 acres, 2024-10-12 to
2026-10-12). All checks ran on an isolated copy of the store (`.local-ui-check/audit/`); your saved reports were
only read.

## 1. Fixed and verified

- [x] **Area-development display (J-59)**: no "-0.0"; shares to one decimal; the trend is named as the all-years fit;
  dense areas are not called empty; missing regional data names the exact install command. Dataset audit in
  [DATASETS.md](DATASETS.md).
- [x] **Land prices removed from this version (J-58)**: no price section, price finding, price import page,
  workspace property box or valuation API. Price never affected BUY / WAIT / AVOID. The module stays unused in
  `valuation/`.
- [x] **Findings with sources and next steps (J-57)**
  - One row per check (title, RERA, river flooding, water history, rainfall/coastal, area development, the plot
    itself, access) with status, how it is known, source, date and next step. Missing evidence is "unknown".
  - Evidence: full browser workflow on 2026-10-25 (search, draw, analyse, report, re-evaluate, scenario).
- [x] **Failure handling (J-57)**: a stopped service is named with the fix ("terrascope.cmd start"); failed re-runs
  can be retried; uploads refuse empty files and unknown parcels.
- [x] **Buy or wait from the history of the plot and its surroundings (J-56)**
  - Behaviour:
    - Land cover 2017-2023 (10 m, India-wide, no account) for the plot, within 1 km and 1-3 km. The built-up
      trend scores Area growth.
    - BUY at composite 75 or more, else WAIT. AVOID only on proven legal risk or red flags from the plot's
      history (frequent modelled river flooding, a likely tank or lake bed).
    - Unverifiable title is a "before you pay" checklist, not a blocker.
  - Evidence (2026-10-20, audit copy): VIT BUY 94; Kelambakkam AVOID (91% flooded at 1-in-10); rural
    Tiruvannamalai WAIT 19. Before this, all 58 saved evaluations were "insufficient evidence".
- [x] **Accessibility limits work and are visible (J-46)**
  - Behaviour:
    - Road and school distance limits are in the evaluation drawer and in Scenario mode.
    - Each sub-score falls to 0 at its limit.
    - Distances are measured from the drawn boundary, with the centroid distance alongside; older snapshots
      say they use the centroid.
    - Unknown or invalid preferences get a 422 instead of being dropped silently.
  - Evidence (2026-10-12):
    - VIT: 91.64 at 3,000/5,000 m and 57.39 at 500/1,000 m (contribution 22.91 → 14.35).
    - The snapshot was byte-identical after re-evaluation, and the price response did not change.
    - The browser Scenario drawer showed the same 57.39 → 91.64.
    - A new Katpadi plot: road 0 m from the boundary (a mapped way crosses it), 40 m from the centroid.
- [x] **Flood figures and wording (J-47, J-48)**
  - 1-in-75 reads 1.33%. Every AEP is exact and labelled as the probability of the modelled event, not of
    this parcel flooding.
  - "Hazard-map cells read for 100% of the parcel: 6 cells of about 0.8 ha (parcel 1.1 ha)", with the river-only
    scope stated. Cells with no modelled depth read "none modelled", not 0.
  - Surface water reads 1.5% everywhere. "Parcel + 500 m" is defined.
  - NRSC: "No permitted machine-readable source integrated", with what was investigated.
  - Layout: one headline, a compact table and one expandable method section; no flood score.
  - The surface-water text is no longer truncated when saved; old truncated text is marked as such.
- [x] **Rule-based summary labelled honestly, with evidence references (J-49)**
  - "Assessment summary · rule-based, not AI" unless an AI call succeeded (`explanation_source`).
  - VIT: 5 references, each tied to an evidence row.
  - **Browser, synthetic 3-page PDF:** survey 123/4A and the village were cited on page 2, and legal stayed
    "user-provided, not verified".
- [x] **Satellite change signal (J-50, J-51)**
  - The whole catalogue is read (136 scenes for VIT, not the newest 100), with one scene per season anchor.
  - Scenes must cover the whole parcel, and at least 50% of its full footprint must be clear.
  - Measurement: reflectance offset removed; cloud mask and SWIR on the 10 m grid.
  - Result: same-season comparison, giving no change, a change class, or inconclusive. No confidence
    percentage.
  - **VIT:** no material change (3 pairs, all within ±0.05). Several other test parcels read "inconclusive".
  - **Old reports:** explained as the superseded v1 method, including the 100-scene limit.
  - **Deadline:** reads stop starting at the evidence deadline, and concurrent scene reads are capped, so a
    timeout no longer saturates the link.
- [x] **Legal status and survey-details workflow (J-53)**
  - RERA names the Tamil Nadu authority as not integrated; MahaRERA applies only to Maharashtra.
  - The state comes from the boundary when geocoding gives none.
  - Survey identifiers and typed documents are stored as unverified claims and never become land records.
- [x] **Report clarity (J-54)**
  - "Scored: 25% of your weighting" vs "Measured: 9 of 12 evidence fields", with the denominators.
  - Short place-name heading; one price reason plus a next step; a price-basis selector.
  - A re-evaluation banner on older evaluations; reports reopen after a browser refresh.
- [x] **Price import workflow (J-52)**: removed from the app in J-58; history below
  - Preview with per-line reasons, duplicates, stale and coarse flags and groups; commit with backup and
    re-validation; a "Price data" page; comparables listed under estimates.
  - Verified with a synthetic CSV against an audit-only price file, which was then deleted.
- [x] **Local setup, start and stop**
  - `terrascope.cmd start | stop | status | fetch-data [region]`.
  - 2026-10-12: about ten stop/start cycles on the audit store; afterwards a normal `start` served your
    original store unchanged (see section 5).
- [x] **India-wide coverage**
  - Puducherry, Patna and Kadapa (no regional cache) analysed; Colombo refused in 0.26-0.82 s.
- [x] **Search autocomplete**
  - Local index only. 2026-10-12 browser check: "katpadi" gave 5 suggestions, and only `/search/suggest` was
    called.
- [x] **Map and boundary drawing**
  - 2026-10-12 browser check: drew a 0.09 ha plot, edited it to 0.14 ha and saved, then analysed it.
- [x] **Invalid and outside-coverage polygons**
  - J-38; integration suite.
- [x] **Saved reports and reopening**
  - Reopen p50 9 ms. A refresh reopens the open report (URL hash).
- [x] **Tests (2026-10-12)**
  - data-pipeline 75, ml-models 51, backend-api 11, valuation 52.
  - Integration: 17 passed, 1 skipped (needs real price data).
  - Frontend type-check and production build pass.

## 2. Implemented but not validated

- [x] **AI explanation path**: verified 2026-10-19 with the configured Groq key and the VIT fixture; the
  merged evaluation path returned a non-empty model-generated explanation. Groq explains the deterministic
  scores and recommendation; it does not change them.
- [ ] **Buy/wait thresholds** (J-56): +2 points a year for full growth, BUY at 75, flood flag at 25% of the
  plot at 1-in-100, water bed at 10% occurrence. All are rules, not calibrated against sale prices.
- [ ] **Change-test thresholds**: ±0.05 for stable and 0.10 for change are fixed rules, not calibrated against
  labelled change data.
- [ ] **Prediction quality** (valuation module, unused since J-58): the evaluation harness exists; zero real observations, so no metric is quoted
  (J-42).
- [ ] **Docker Compose path**: unverified (J-04, J-05).
- [ ] **Screen-reader and contrast audit**: not done. Labels were added where checks found gaps.
- [x] **Warm-analysis cache implemented**: JRC surface-water and Copernicus DEM parcel results now use a
  versioned, 30-day on-disk cache keyed by the exact polygon and data source version. Provider failures are
  never cached. A regression test confirms a repeated parcel read does not reopen the raster.

## 3. Blocked by missing external data or access

- [ ] **Land prices: out of scope for this version (J-58); no permitted dataset.** The verified terms and the smallest input needed are in
  [SETUP_VALUATION.md](SETUP_VALUATION.md).
  - **TNREGINET guideline values:** reproduction needs the Registration Department's permission (verified in
    its copyright policy).
  - **Listing portals:** need written licences.
  - **Owner or broker rows:** work today, but none have been supplied.
- [ ] **Land records, encumbrance and approvals:** no permitted source is integrated, so Legal Safety stays
  unscored.
- [ ] **Tamil Nadu RERA (TNRERA) data:** not integrated.
- [ ] **Growth, economic side:** area growth is now scored from observed development (J-56). Registered sale
  counts, master-plan zoning, committed infrastructure and population/employment are still not integrated.
- [ ] **Flood:**
  - Rainfall/pluvial and coastal datasets are not integrated.
  - NRSC historical footprints: no permitted machine-readable source found (J-32).

## 4. Still failing or open

- [ ] **Warm analyses outside installed regions are slow**: the remote DEM and GSW layers now have a persistent
  parcel-result cache, but a real Kadapa/Patna timing run is still needed before this performance item can be
  marked verified.
- [ ] **Monsoon anchors**: often no clear scene (VIT: none near 2025-08-26), so a parcel can have fewer than 4
  seasonal pairs.
- [ ] **Browser screenshots in the app pane**: still partial (J-45). Most UI checks are DOM/text checks.

## 6. Verification after NSB PR #1

- PR #1 merged into `main` without conflicts.
- Valuation tests: 52 passed locally.
- Frontend TypeScript check and production build: passed locally.
- Python compile check across backend, data-pipeline, ML, and valuation: passed locally.
- Docker-backed verification remains open because Docker Desktop was unavailable during this check.

## 5. Your saved reports

- Before this work: 93 snapshots, 93 parcels, 58 evaluations, 9 documents in `.local-ui-check/backend.sqlite3`.
- A byte copy was kept as `backend.sqlite3.backup-2026-10-12`.
- All tests and generated reports used `.local-ui-check/audit/backend-audit-2026-10-12.sqlite3`.
- On the first normal start, the store gains an empty `land_details` table and a nullable `documents.doc_type`
  column. This is additive; no rows change.

## Measurements (2026-10-12, same machine and Wi-Fi link, test geometry, not surveyed boundaries)

| What | Before | After | Sample |
|---|---|---|---|
| Analysis, cold (new parcel), median | 35.9 s, satellite dropped at the deadline (2026-10-12, before J-51); 12.4 s on 2026-10-11 | 13.6 s (4.9-21.8 s), satellite completed for all | 7 India parcels, polygons shifted so run 1 is cold |
| Analysis, warm, median | 0.66 s (2026-10-11) | 0.43 s | same 7 parcels, run 2 |
| Exact VIT polygon, warm | 4.4-7.6 s (geocoding not cached) | 0.49 s (1.22 s on the first run after a restart) | 2 runs each |
| Satellite series, cold, VIT polygon, cache off | 52.1 s and 36.9 s, with 1-2 failed reads (old connector) | 22.6 s and 28.0 s, no failures | interleaved A/B, same network |
| Evaluation, p50 | 0.24 s (2026-10-11) | 0.26 s | n=14 |
| Saved-report reopen, API p50 | 6 ms | 9 ms | n=14 |
| Search suggestion | local index (J-36) | unchanged | — |
| Errors / timeouts | SSL EOFs and dropped connections while saturated | 0 | benchmark runs |
