# TerraScope land valuation

A transparent, comparable-property price range for a drawn parcel, or an explicit refusal. It is independent of
everything else: suitability weights, flood evidence and legal status never move a price, and a price never
moves them.

**No real price data ships with TerraScope.** Today every parcel is refused with `no_price_data`. Where the data
would have to come from, and what blocks it, is in [../docs/SETUP_VALUATION.md](../docs/SETUP_VALUATION.md).

## Price types are never pooled

| `price_type` | Meaning | Report title |
|---|---|---|
| `asking` | a seller's asking price from a listing; not a sale | "Listing-based estimated price range" |
| `transaction` | a completed, registered sale price | "Sale-based estimated price range" |
| `guideline` | a government guideline / circle rate: an administrative floor | "Government guideline value (reference)" |

## Observation contract (CSV, one row per observation)

Headers are normalised (case, punctuation). Required columns:

| Column | Notes |
|---|---|
| `source`, `source_record_id` | provider name and its record id |
| `reuse_basis` | the licence or permission under which the row may be used; rows without it are dropped |
| `price_type` | `asking`, `transaction` or `guideline` |
| `observed_date`, `retrieved_date` | when listed / registered / effective, and when retrieved |
| `price_value`, `price_unit`, `currency` | `price_unit` is `total` or `per_<unit>`; only `INR` is accepted, never converted |
| `property_category` | `vacant_plot`, `agricultural_land`; built property (`apartment`, `independent_house`, `villa`, `commercial_building`, `other`) is dropped |
| `land_use` | `residential`, `commercial`, `industrial`, `agricultural`, `mixed_use` |
| `latitude`, `longitude`, `location_precision` | precision `exact`, `street`, `locality`, `pincode`, `district`; only the first three are used as comparables |

Optional columns:

- `source_url`
- `area_value` and `area_unit` (required for `total` prices)
- `district`, `state`, `locality`
- `attributes`: kept verbatim, never inferred
- `property_ref`: a survey or plot number that identifies the plot

Area units: `sqft`, `sqm`, `sqyd`, `acre`, `hectare`, `cent`, `guntha`, `ground`, `kanal`, `marla`. Bigha, katha
and similar units vary by state, so they are rejected rather than converted with a guessed factor.

### Importing

- **Preview** with `Price data` on the start page, or `POST /api/v1/valuation/import/preview`. It writes nothing
  and reports every CSV line's fate:
  - rejected, with the reason;
  - a repeat of another record, or a re-listing of the same plot, with the line that was kept;
  - stale (asking older than 18 months; sale or guideline older than 3 years);
  - dated in the future, or located only to a PIN code or district (kept, but not a comparable);
  - groups by price type × land use × category, which are never pooled;
  - sources with their stated permissions;
  - the first 50 normalised rows (₹/sq ft, sq ft).
- **Commit** with `POST /api/v1/valuation/import/commit` (`permission_confirmed=true`). It:
  - appends the rows that passed to the served file;
  - keeps `observations.csv.bak-<time>`;
  - re-validates the combined file before replacing it.
- **Command line:** `python -m valuation.dataset file.csv` prints the same per-row reasons.

### Cleaning

Every dropped row is counted by reason (`python -m valuation.dataset file.csv`). Rows are dropped for:

- missing provenance;
- a non-INR currency;
- an unknown category, use or precision;
- coordinates outside India;
- unparseable dates, or retrieval before observation;
- a price or area outside the plausibility bounds (these catch lakh/crore and unit slips);
- a total price without an area;
- built property.

De-duplication:

- The same record delivered twice keeps its latest retrieval.
- Re-listings of one plot, from any source and at any date, collapse to the most recent observation. They
  are recognised when:
  - exact points lie within 25 m with the area within 3%; or
  - street- or locality-level points lie within 75 m, with the area within 1% and the price within 3%, inside
    a year; or
  - rows share a `property_ref` within a district. Different `property_ref` values are never merged.
- Without identifiers, adjacent same-size layout plots within 25 m may be merged. This is deliberate: it costs
  comparables but keeps one property from sitting on both sides of a validation split.

## Estimate (comparable baseline)

Comparables share:

- the price type, land use and land category;
- comparable location precision;
- a date no later than the valuation date, and not older than 18 months (asking) or 3 years (transaction,
  guideline);
- a similar size: from one third to three times the parcel's area.

They are taken from the smallest radius (1, 2, 5, 10 km) holding at least 5 of them.

The result is:

- the median ₹/sq ft;
- the interquartile and full spread. This is the comparables' own spread, **not a statistically validated
  prediction interval**;
- a total only when the parcel lies within the comparables' size range;
- every comparable with its provenance;
- reasons for uncertainty.

Prices are not adjusted for time. Plot facts that are not in the data (road frontage, shape, approvals, title)
are not invented.

Refusals: `no_price_data`, `price_type_not_covered`, `land_use_not_covered`, `no_comparables_nearby`,
`stale_data_only`, `area_outside_support` (e.g. a campus valued from house plots), `insufficient_comparables`.
`invalid_input` returns HTTP 400.

## Measuring prediction quality

`python -m valuation.evaluate observations.csv --price-type asking`:

- **Leakage:** re-listings are collapsed before splitting, and the harness asserts that no property sits on
  both sides of a split.
- **Holdouts:**
  - temporal: train on observations up to the 80th-percentile date, test on later ones (needs 6+ months);
  - geographic: whole districts, or 10 km cells, held out (needs 4+ areas).
- **Baseline:** draws comparables from the training half only, as of each test observation's date.
- **Model:** a gradient-boosting model (lat, lon, log area, land use, date) is compared only when there are
  300+ training rows. Its encoder is fitted on training rows; the hyperparameters are fixed, not tuned.
- **Reported:**
  - train and test counts and dates, regions, land uses;
  - MAE, RMSE (₹/sq ft), median absolute percentage error (no exclusions: cleaned targets are all positive);
  - the share of predictions within ±10/20/30%;
  - prediction coverage (estimates vs refusals by reason);
  - how often the interquartile spread contained the held-out price;
  - the model compared with the baseline.
- **Labelling:** every figure names its target (`asking` or `transaction`). Accuracy against listings is not
  accuracy against sale prices.
- **Threshold:** below 30 held-out estimates the result is `not_yet_validated`, and no error figure is quoted.

Current status: **not yet validated**, because there are zero real observations.

Synthetic self-check (test data only, not accuracy):

- A 600-plot synthetic market confirms that the harness separates properties across splits.
- Held-out towns are refused rather than guessed.
- The interquartile spread contained only about 21% of held-out synthetic prices. That is why it is never
  called an interval.

## Serving

- `GET /api/v1/valuation/data`: what is loaded, from which sources, and the validation status.
- `POST /api/v1/valuation/estimate` with `{latitude, longitude, area_sqft, land_use, price_basis}`.
  `price_basis` is `asking` by default.

## Tests

`python -m pytest valuation -q`. These use synthetic rows written in the test file.
