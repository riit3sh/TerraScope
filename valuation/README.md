# TerraScope land valuation

Estimates market price per square foot and total value for a drawn parcel.

This module is **independent of the suitability scoring engine**. Suitability
weights say what a particular buyer wants; they must never change an estimate of
what the market pays. Changing a preference slider re-scores a parcel and leaves
its valuation untouched.

## Status: no real dataset is shipped

The repository contains **no real land-price data and no model trained on real
data.** The import, training, serving and UI path is complete and tested, but it
currently runs on a clearly-labelled synthetic fixture
(`fixtures/synthetic_land_prices.csv`, every row stamped `SYNTHETIC_FIXTURE`).

Any prediction made from that fixture carries `is_synthetic: true` all the way
to the UI, where it is labelled demo data. **Do not present it as a valuation.**
To get real numbers, supply a real CSV and retrain (below).

## What you need to supply

One CSV, one row per observed land price. Minimum useful dataset:

| Requirement | Minimum | Why |
|---|---|---|
| Usable rows after import | 50 | below this, training is refused |
| Rows for the holdout | 10 | below this, no error figure is quoted |
| Distinct months **or** distinct districts | 6 months, or 4 districts | needed for a temporal or geographic holdout |
| Coverage near your parcels | ≥5 observations within 25 km | otherwise the location is refused |

Good dataset properties, in rough order of value:

1. **Completed transactions** (registry/sub-registrar data) rather than asking
   prices. Portal listings are asking prices; record them as such.
2. **A real time span** — 3+ years lets the model see price drift, and enables
   the temporal holdout, which is the honest test for a forecasting task.
3. **Several districts**, so geography is a signal rather than a constant.
4. **Plot-level coordinates.** District centroids for every row make the spatial
   features meaningless.

Candidate sources: state sub-registrar / IGR transaction exports (Maharashtra
IGR, TN Registration Dept), municipal circle-rate / ready-reckoner tables (these
are floors, not market prices — label them clearly), or a licensed listings feed.

## CSV contract

Headers are normalized (lowercased, non-alphanumerics to `_`), so
`Price Value` and `price_value` both work. All 13 columns are required.

| Column | Type | Notes |
|---|---|---|
| `record_id` | string | your identifier for the observation |
| `latitude` | float | −90..90, plot-level if possible |
| `longitude` | float | −180..180 |
| `district` | string | used for the baseline and the coverage report |
| `state` | string | |
| `area_value` | float > 0 | in `area_unit` |
| `area_unit` | enum | `sqft`, `sqyd`, `sqm`, `acre`, `hectare`, `cent`, `guntha`, `ground`, `kanal`, `marla` |
| `land_use` | enum | `residential`, `commercial`, `industrial`, `agricultural`, `mixed_use` |
| `observation_date` | date | when the price was observed |
| `price_value` | float > 0 | in `price_unit` |
| `price_unit` | enum | `total_inr`, `inr_per_sqft`, `inr_per_sqm`, `inr_per_acre`, `inr_per_cent` |
| `price_basis` | enum | `asking` or `transaction` — do not guess |
| `source` | string | provenance, carried into the coverage report |

**`bigha` and `katha` are deliberately rejected.** Their size varies by state and
district, so converting them centrally would silently corrupt areas. Convert
those rows to `sqft` yourself, using the right local factor, before importing.

Rows failing any rule are dropped and counted by reason in the import report;
they never silently become training data.

### Duplicate handling

Re-listings of one plot would otherwise put the same property in both the
training and holdout halves and flatter the error. Rows are collapsed onto a
`property_key` (coordinates rounded to ~11 m, area to the nearest 10 sqft, plus
land use) and only the most recent observation per property is kept. Training
aborts if any property still appears on both sides of the split.

## Training

```bash
python -m valuation.train path/to/land_prices.csv --out valuation/artifacts/land_price_model.joblib
```

Add `--synthetic` only for invented data; it flags every downstream prediction
as demo-only.

The run prints the measured holdout report and writes the artifact plus a
`.metadata.json` beside it. It compares two models:

- **Baseline** — district median INR/sqft (global median for unseen districts).
- **Model** — `HistGradientBoostingRegressor` over latitude, longitude, area,
  land use, price basis and observation year/month.

Both are scored on the same held-out rows, and MAE / RMSE / median APE are
reported for each. A model that fails to beat the baseline is still written, with
`model_beats_baseline: false` — that is a real result about your dataset.

### Prediction range

Two extra quantile models (0.1 / 0.9) give an 80% interval. Its **measured**
coverage on the holdout is recorded, and the range is only served when it
achieves at least 75% of its nominal coverage. On the synthetic fixture it does
not (80% nominal, ~31% measured, because prices drift upward and the quantile
models are fit on older data), so no range is shown and the API says why.

## Serving

`POST /api/v1/valuation/estimate` and `GET /api/v1/valuation/model`.

A prediction is refused, with an explicit status, when:

| Reason | Meaning |
|---|---|
| `model_not_trained` | no artifact — train one |
| `location_not_covered` | fewer than 5 observations within 25 km |
| `land_use_not_covered` | dataset has no rows of that land use |
| `unsupported_land_use` / `invalid_input` | bad request |

Tune with `VALUATION_MAX_SUPPORT_DISTANCE_KM`, `VALUATION_MIN_SUPPORTING_OBSERVATIONS`
and `VALUATION_MODEL_PATH`.

Every successful response carries `model_version`, `data_version`,
`valuation_date`, the measured `accuracy` block and an `evidence_coverage` block
naming how much data actually stood behind it.

## Tests

```bash
python -m pytest valuation/test_valuation.py -v
```
