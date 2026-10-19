"""Measure prediction quality on held-out observations, honestly.

    python -m valuation.evaluate observations.csv [--price-type asking] [--out report.json]

- Re-listings are collapsed into one property before splitting (dataset.py), so a
  property can never sit in both the training and the test half.
- Holdouts: temporal (train on the past, test on the latest 20%) and geographic
  (whole districts, or 10 km cells when districts are missing, held out).
- The comparable baseline draws comparables from the training half only. A
  gradient-boosting model is compared against it only when the training half is
  large enough, and all of its preprocessing is fitted on the training half.
- Metrics are labelled by their target (asking or transaction prices). Below
  MIN_TEST_ESTIMATES held-out estimates the result is "not yet validated" and no
  error figures are quoted.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from .comparables import ValuationUnavailable, estimate
from .dataset import PRICE_TYPE_LABELS, load_observations

MIN_TEST_ESTIMATES = 30
MIN_TRAIN_FOR_MODEL = 300
MIN_MONTHS_FOR_TEMPORAL = 6
MIN_GROUPS_FOR_GEOGRAPHIC = 4


def metrics(actual: np.ndarray, predicted: np.ndarray) -> dict[str, float]:
    actual, predicted = np.asarray(actual, dtype=float), np.asarray(predicted, dtype=float)
    ape = np.abs(predicted - actual) / actual  # targets are > 0 after cleaning, so nothing is excluded
    return {
        "mae_inr_per_sqft": round(float(np.mean(np.abs(predicted - actual))), 2),
        "rmse_inr_per_sqft": round(float(np.sqrt(np.mean((predicted - actual) ** 2))), 2),
        "median_ape_pct": round(float(np.median(ape) * 100), 2),
        "within_10_pct": round(float(np.mean(ape <= 0.10) * 100), 1),
        "within_20_pct": round(float(np.mean(ape <= 0.20) * 100), 1),
        "within_30_pct": round(float(np.mean(ape <= 0.30) * 100), 1),
    }


def splits(frame: pd.DataFrame) -> list[tuple[str, str, pd.Index, pd.Index]]:
    out = []
    if frame["observed_date"].dt.to_period("M").nunique() >= MIN_MONTHS_FOR_TEMPORAL:
        cutoff = frame["observed_date"].quantile(0.8)
        out.append(("temporal", f"trained on observations up to {cutoff.date()}, tested on later ones",
                    frame.index[frame["observed_date"] <= cutoff], frame.index[frame["observed_date"] > cutoff]))
    district = frame["district"].str.casefold()
    cell = (frame["latitude"] // 0.09).astype(int).astype(str) + ":" + (frame["longitude"] // 0.09).astype(int).astype(str)
    area_key = district.where(district != "", "cell " + cell)
    keys = area_key.value_counts().index.tolist()
    if len(keys) >= MIN_GROUPS_FOR_GEOGRAPHIC:
        held = set(keys[::4])
        mask = area_key.isin(held)
        out.append(("geographic", f"{len(held)} of {len(keys)} districts / 10 km cells held out entirely",
                    frame.index[~mask], frame.index[mask]))
    return out


def _gbm(train: pd.DataFrame, test: pd.DataFrame) -> np.ndarray:
    from sklearn.ensemble import HistGradientBoostingRegressor
    from sklearn.preprocessing import OrdinalEncoder

    def features(f: pd.DataFrame) -> pd.DataFrame:
        return pd.DataFrame({
            "latitude": f["latitude"], "longitude": f["longitude"], "log_area": np.log(f["area_sqft"]),
            "land_use": f["land_use"], "t": f["observed_date"].dt.year + f["observed_date"].dt.dayofyear / 366,
        })

    encoder = OrdinalEncoder(handle_unknown="use_encoded_value", unknown_value=-1).fit(train[["land_use"]])
    x_train, x_test = features(train), features(test)
    x_train["land_use"] = encoder.transform(train[["land_use"]]).ravel()
    x_test["land_use"] = encoder.transform(test[["land_use"]]).ravel()
    model = HistGradientBoostingRegressor(max_iter=300, learning_rate=0.06, min_samples_leaf=10,
                                          categorical_features=[3], random_state=17)
    model.fit(x_train.to_numpy(float), np.log(train["price_inr_per_sqft"].to_numpy(float)))
    return np.exp(model.predict(x_test.to_numpy(float)))


def evaluate_split(frame: pd.DataFrame, train_index: pd.Index, test_index: pd.Index) -> dict[str, Any]:
    train, test = frame.loc[train_index], frame.loc[test_index]
    assert not set(train["group_id"]) & set(test["group_id"]), "a property sits on both sides of the split"
    test = test[test["area_sqft"].notna()]
    predicted, spreads, refusals = {}, {}, {}
    for index, row in test.iterrows():
        try:
            result = estimate(train, latitude=row["latitude"], longitude=row["longitude"], area_sqft=row["area_sqft"],
                              land_use=row["land_use"], price_type=row["price_type"],
                              valuation_date=row["observed_date"].date())
        except ValuationUnavailable as refusal:
            refusals[refusal.reason] = refusals.get(refusal.reason, 0) + 1
            continue
        predicted[index] = result["estimate_inr_per_sqft"]
        spreads[index] = (result["spread_inr_per_sqft"]["p25"], result["spread_inr_per_sqft"]["p75"])
    answered = pd.Index(list(predicted))
    actual = test.loc[answered, "price_inr_per_sqft"].to_numpy(float)
    validated = len(answered) >= MIN_TEST_ESTIMATES
    out: dict[str, Any] = {
        "train_observations": int(len(train)),
        "test_observations": int(len(test)),
        "train_dates": [train["observed_date"].min().date().isoformat(), train["observed_date"].max().date().isoformat()],
        "test_dates": [test["observed_date"].min().date().isoformat(), test["observed_date"].max().date().isoformat()] if len(test) else None,
        "estimates": int(len(answered)),
        "refusals": refusals,
        "prediction_coverage_pct": round(100 * len(answered) / len(test), 1) if len(test) else None,
        "status": "validated" if validated else "not_yet_validated",
        "baseline": None,
        "baseline_spread": None,
        "model": None,
    }
    if not validated:
        out["note"] = (f"Only {len(answered)} held-out estimates (need {MIN_TEST_ESTIMATES}); error figures from so "
                       "few cases would be unreliable, so none are quoted.")
        return out
    out["baseline"] = metrics(actual, [predicted[i] for i in answered])
    low = np.array([spreads[i][0] for i in answered])
    high = np.array([spreads[i][1] for i in answered])
    out["baseline_spread"] = {
        "share_of_targets_inside_p25_p75_pct": round(float(np.mean((actual >= low) & (actual <= high)) * 100), 1),
        "median_width_pct_of_estimate": round(float(np.median((high - low) / np.array([predicted[i] for i in answered])) * 100), 1),
        "note": "The comparables' interquartile spread is not a calibrated interval; this measures how often it happened to contain the held-out price.",
    }
    model_train = train[train["area_sqft"].notna()]
    if len(model_train) >= MIN_TRAIN_FOR_MODEL:
        model_predicted = _gbm(model_train, test.loc[answered])
        out["model"] = {"name": "HistGradientBoostingRegressor on lat, lon, log area, land use, date",
                        **metrics(actual, model_predicted),
                        "beats_baseline_on_mae": bool(np.mean(np.abs(model_predicted - actual))
                                                      < out["baseline"]["mae_inr_per_sqft"])}
    else:
        out["model"] = {"skipped": f"{len(model_train)} training rows; a model is only compared from {MIN_TRAIN_FOR_MODEL}."}
    return out


def evaluate(frame: pd.DataFrame, price_type: str = "asking") -> dict[str, Any]:
    subset = frame[frame["price_type"] == price_type]
    report: dict[str, Any] = {
        "target": price_type,
        "target_label": PRICE_TYPE_LABELS[price_type],
        "observations": int(len(subset)),
        "regions": sorted(set(subset["state"]) - {""}),
        "land_uses": {k: int(v) for k, v in subset["land_use"].value_counts().items()},
        "dates": [subset["observed_date"].min().date().isoformat(), subset["observed_date"].max().date().isoformat()] if len(subset) else None,
        "holdouts": {},
    }
    for name, description, train_index, test_index in splits(subset):
        report["holdouts"][name] = {"description": description, **evaluate_split(subset, train_index, test_index)}
    statuses = [h["status"] for h in report["holdouts"].values()]
    report["status"] = "validated" if statuses and all(s == "validated" for s in statuses) else "not_yet_validated"
    if not report["holdouts"]:
        report["note"] = (f"{len(subset)} {price_type} observations support neither a temporal holdout "
                          f"({MIN_MONTHS_FOR_TEMPORAL}+ months) nor a geographic one ({MIN_GROUPS_FOR_GEOGRAPHIC}+ areas).")
    return report


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("csv")
    parser.add_argument("--price-type", default="asking", choices=sorted(PRICE_TYPE_LABELS))
    parser.add_argument("--out", help="write the JSON report here (default: <csv>.quality-<price type>.json)")
    args = parser.parse_args()
    cleaned, import_report = load_observations(args.csv)
    result = {"import": import_report.as_dict(), **evaluate(cleaned, args.price_type)}
    target = Path(args.out or f"{args.csv}.quality-{args.price_type}.json")
    target.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))
