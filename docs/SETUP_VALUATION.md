# Price data for TerraScope (operators)

Operator instructions live here, not in the report. A report says only whether a price is available and why.

## Current state (2026-10-11)

**No real price data is loaded, so every parcel gets "No price estimate".** The pipeline is complete and tested on
synthetic rows:

- import and cleaning;
- comparable-property estimate;
- refusals;
- holdout evaluation;
- UI.

It is not validated on real data.

## Where the data must come from

| Route | Status (checked 2026-10-11) | What is needed |
|---|---|---|
| Listing portals (99acres, MagicBricks, Housing.com) | No public API or data licence found. Their terms pages refused automated retrieval (HTTP 403 / blocked), and only third-party scraping services advertise this data. Scraping without permission is not done. | A written data licence or partnership from a portal. This is a paid or contractual decision for you. |
| Licensed aggregators of registration data (e.g. Square Yards' IGR-based data) | Commercial products; licence terms not published. Not contacted. | Your approval to contact them and pay. Then use the `transaction` price type. |
| State registration departments (IGR Maharashtra, TNREGINET, Kaveri/IGR Karnataka, IGRS AP/Telangana) | Public access is per-document or per-street lookup, often behind a captcha. No bulk open release found. | An authorised bulk export or a formal data request to the department. |
| Government guideline values | TNREGINET and Kaveri offer street/survey lookups. OpenCity re-hosts Bengaluru guidance-value circulars (Sept 2023 PDFs from igr.karnataka.gov.in, licence field "Other (Public Domain)"). | Could be imported as `guideline` rows after PDF extraction and locality geocoding. Not done: Bengaluru only, 2023, and these are administrative floors, not market prices. |
| data.gov.in | The search page refused automated access (HTTP 403). No guideline-value or circle-rate dataset appeared in web searches. | Manual check of the portal. |
| Owner- or broker-supplied listings | Supported now. | Rows with `reuse_basis` naming the permission (for example "owner email 2026-10-01"). |

Publicly visible listings are not a free database. TerraScope does not bypass logins, captchas, paywalls or
terms of use.

## Loading data

1. Put a CSV following [../valuation/README.md](../valuation/README.md) at `data-cache/valuation/observations.csv`
   (git-ignored), or set `VALUATION_OBSERVATIONS_PATH`.
2. Check it: `python -m valuation.dataset path/to/observations.csv` prints what was kept and why rows were dropped.
3. Measure it: `python -m valuation.evaluate path/to/observations.csv --price-type asking`. This writes
   `<csv>.quality-asking.json` next to the data. Every estimate then carries that validation status.
4. Restart the backend, or just replace the file; it is reloaded when its modification time changes.

## Environment

| Variable | Default | Meaning |
|---|---|---|
| `VALUATION_OBSERVATIONS_PATH` | `data-cache/valuation/observations.csv` | the observations served |
| `TERRASCOPE_DATA_DIR` | `data-cache` | root for the default path |
