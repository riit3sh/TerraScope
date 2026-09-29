# Valuation setup (operators)

Operator instructions live here, not in the report UI. A user looking at a parcel
report should see *whether* a price is available and why — never a training command.

## Current state

Valuation is **off for real reports**. The only model in the repository was fitted
on `valuation/fixtures/synthetic_land_prices.csv`, whose rows are invented. Serving
those numbers would be presenting fiction as a market price, so `estimate_value`
refuses with `reason: synthetic_model_only`.

`VALUATION_ALLOW_SYNTHETIC=true` re-enables them **for demo purposes only**. Every
response is then flagged `is_synthetic: true` and banner-labelled DEMO DATA in the
UI. Do not set this in anything a stakeholder will read.

## What a real dataset must provide

Before any price is shown, a regional dataset is needed with documented provenance
and a held-out evaluation. The import contract (13 columns) is in
[../valuation/README.md](../valuation/README.md).

| Requirement | Minimum | Why |
|---|---|---|
| Usable rows after import | 50 | below this, training is refused |
| Holdout rows | 10 | below this, no error figure is quoted |
| Distinct months **or** districts | 6 months, or 4 districts | needed for a temporal or geographic holdout |
| Observations within 25 km of the parcel | 5 | otherwise the location is refused |

### Provenance to record for each source

State the issuing authority, the extraction date, the licence, and whether each
row is an **asking price** or a **completed transaction**. Portal listings are
asking prices and must be labelled as such; circle-rate / ready-reckoner tables
are administrative floors, not market prices, and must not be mixed in unlabelled.

Candidate sources for the parcels currently being tested:

- **Andhra Pradesh** — Registration & Stamps Dept (IGRS AP) market-value and
  registered-document data. Requires authorised access; there is no open public API.
- **Maharashtra** — IGR Maharashtra registered-transaction exports.
- **Tamil Nadu** — TN Registration Dept (TNREGINET) guideline values and documents.

Where no integration is authorised, accept user-provided documents instead and
record them as user-supplied and unverified. Do not imply a public API exists.

## Training

```bash
python -m valuation.train path/to/real_land_prices.csv --out valuation/artifacts/land_price_model.joblib
```

Omit `--synthetic` for real data. The run prints the measured holdout report
(baseline vs model MAE/RMSE, interval coverage) and writes a `.metadata.json`
beside the artifact. A model that fails to beat the district-median baseline is
still written, with `model_beats_baseline: false` — that is a real result about
the dataset, not a reason to hide it.

## Environment

| Variable | Default | Meaning |
|---|---|---|
| `VALUATION_MODEL_PATH` | `valuation/artifacts/land_price_model.joblib` | artifact to serve |
| `VALUATION_ALLOW_SYNTHETIC` | unset (off) | demo-only; serves synthetic figures |
| `VALUATION_MAX_SUPPORT_DISTANCE_KM` | 25 | radius for the coverage check |
| `VALUATION_MIN_SUPPORTING_OBSERVATIONS` | 5 | minimum nearby observations |
