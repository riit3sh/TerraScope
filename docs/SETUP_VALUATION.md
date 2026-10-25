# Price data for TerraScope (operators)

**Not used in this version.** Land prices were removed from TerraScope's report, analysis flow and API on 2026-10-25 (journey J-58): no permitted, verified price data exists. This is kept, unused, for a later version.

Operator instructions live here, not in the report. A report says only whether a price is available, why, and
the next step.

## Current state (2026-10-12)

**No permitted price observations are loaded, so every parcel gets "No price estimate".** Nothing below was
bought, requested or scraped. The import workflow is complete and tested on synthetic rows:

- **Preview** (`Price data` on the start page, or `POST /api/v1/valuation/import/preview`). It writes nothing
  and reports, for every CSV line:
  - why a row was rejected;
  - duplicates (the same record twice, or a re-listing of the same plot), and which line was kept;
  - stale rows, future dates and PIN-code/district-only locations, which are kept but not used as comparables;
  - groups by price basis × land use × category (never pooled);
  - sources and their stated permissions;
  - the first 50 normalised rows.
- **Commit** (`POST /api/v1/valuation/import/commit`):
  - needs an explicit permission confirmation;
  - appends only rows that passed;
  - backs up the previous file and re-validates the combined file before replacing it.
- **Estimates** list the comparable properties behind them, with source, record id, permission, date, distance
  and location precision.
- **Command line:** `python -m valuation.dataset file.csv` prints the same per-row reasons.

## Source-access table

Checked 2026-10-12 in a real browser (the app's browser pane), so a bot block was not taken as "no data".
Earlier checks are dated.

| Source and owner | Basis | Coverage and dates | Actual access method | Reuse terms (verified where stated) | Fields available | Exact blocker |
|---|---|---|---|---|---|---|
| [TNREGINET](https://tnreginet.gov.in/portal/), Registration Department, Government of Tamil Nadu (Inspector General of Registration) | Guideline value (administrative floor for stamp duty; not a market price) | All Tamil Nadu, street-wise in towns and survey-number-wise elsewhere. Values in force from 01-07-2024, history from 2002 | Interactive lookup on the home page: district → sub-registrar office → village → street or survey number. No captcha seen on this lookup (the encumbrance-certificate search has one). No bulk download or API found | **Verified in its Copyright Policy page:** contents "may not be reproduced partially or fully, without due permission from Registration department". Contact: IG of Registration, 100 Santhome High Road, Chennai 600028, +91-44-24640160 | Rate per unit area for each street or survey number; no coordinates (needs geocoding of the street, or a village or survey match) | **Written permission from the IG of Registration** to reuse guideline values (for Vellore district at least), or a bulk export from them. Not requested: contacting them needs your approval. |
| [data.gov.in](https://www.data.gov.in) (OGD Platform, NIC) | Any | India | Catalogue search for "guideline value", "circle rate", "land price" and "registration documents stamp duty" | Government Open Data Licence – India, for datasets that exist | Only aggregate datasets (e.g. document counts and stamp-duty revenue by application, 2024-26). No guideline, circle-rate or parcel price dataset | No such dataset is published |
| Tamil Nadu open data portal (tn.data.gov.in) | Any | Tamil Nadu | Web search only (2026-10-12); not browsed directly | OGL listed by a directory; unverified | None found | Not confirmed either way; a manual catalogue check is still open |
| [99acres](https://www.99acres.com/load/Company/termsconditions), Info Edge (India) Ltd | Asking prices (listings) | All India, current listings | Website and apps; no public data API | **Verified in its terms:** copying, extracting or downloading content, or "creating alternate databases", needs IEIL's prior written consent; spiders, robots and crawlers are prohibited | Price, area, locality, sometimes coordinates | A written data licence from Info Edge. This is a paid or contractual decision for you |
| [Housing.com](https://housing.com/terms-of-use), Locon Solutions Pvt Ltd | Asking prices | All India | Website and apps; no public data API | **Verified in its terms:** "data compilations" are the property of the company, its users and its content suppliers, and are copyright-protected; no reuse licence is offered | As for 99acres | A written data licence from Locon Solutions |
| MagicBricks, Times Internet | Asking prices | All India | Website | Not verified: the browser pane blocks this site by policy, and the page fetcher could not load it | As above | Terms unread; the same licence question as the other portals |
| Licensed registration-data aggregators (e.g. Square Yards' IGR-based data, PropEquity, Liases Foras) | Transactions, or derived | Varies | Commercial products | Licence terms not published. Not contacted | Usually transaction price, area, date and project | Your approval to contact them and pay |
| [OpenCity](https://data.opencity.in/dataset/bengaluru-guidance-value-change-circulars-2023), re-hosting IGR Karnataka circulars | Guideline (guidance) value | Bengaluru only, 2023 PDFs | PDF download | OpenCity's metadata says "Other (Public Domain)". IGR Karnataka's own terms are not verified | Rates per locality in PDF tables; no coordinates | Not for any acceptance parcel. It would need PDF extraction and locality geocoding, and gives an administrative floor, not a market price |
| Owner- or broker-supplied rows | Asking or transaction | Wherever supplied | The importer (CSV) | The supplier's written permission, named in `reuse_basis` | Everything in the contract | **None: this works today.** It needs the rows |

Publicly visible listings are not a free database. TerraScope does not bypass logins, captchas, paywalls or terms
of use, and does not scrape.

## The smallest input that unlocks a real estimate

For the **VIT parcel** (2.75 acres, about 119,600 sq ft), comparables must be one third to three times its size,
roughly **0.9 to 8 acres**. House plots of 1,200 to 2,400 sq ft are refused by design: a campus is never valued
from small residential plots.

The smallest useful input is any one of these:

1. **Sales:** a CSV of **at least 5 vacant land sales of 0.9 to 8 acres within 10 km of the parcel**, dated from
   October 2023. Each row needs:
   - sale price and area;
   - date;
   - coordinates, or a survey number plus village;
   - a `reuse_basis` naming the owner's or broker's permission.

   This gives a "Sale-based estimated price range".
2. **Asking prices:** the same with listing prices, at least 5 within 18 months. This gives a "Listing-based
   estimated price range", labelled as asking prices.
3. **Guideline values:** written permission from the IG of Registration, plus the guideline values for the
   parcel's village and survey numbers (or those around it). This gives a "Government guideline value
   (reference)", which is an administrative floor, not a market price.

For a **residential Katpadi plot**, use the same rows with plots of a similar size (for example 5 or more plots of
800 to 7,200 sq ft for a 2,400 sq ft plot).

## Loading data

1. Open `Price data` on the start page, choose the CSV and press Preview. Read the rejected rows and flags.
2. Tick the permission box and add the rows. The previous file is kept as `observations.csv.bak-<time>`.
3. Measure it: `python -m valuation.evaluate data-cache/valuation/observations.csv --price-type transaction`.
   Every estimate then carries that validation status. Below 30 held-out estimates, it stays "not yet
   validated".

Column contract: [../valuation/README.md](../valuation/README.md).

## Environment

| Variable | Default | Meaning |
|---|---|---|
| `VALUATION_OBSERVATIONS_PATH` | `data-cache/valuation/observations.csv` | the observations served and appended to |
| `TERRASCOPE_DATA_DIR` | `data-cache` | root for the default path |
