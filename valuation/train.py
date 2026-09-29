"""Train and evaluate the land-price model against a held-out split.

Every accuracy figure this module reports is measured on data the model did not
see. Nothing here invents a number: when a dataset is too small or too narrow to
support a given validation strategy, the strategy is refused and the report says
so rather than quoting an optimistic in-sample score.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import asdict, dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.preprocessing import OrdinalEncoder

from .dataset import LAND_USES, dataset_version, load_price_csv


LOGGER = logging.getLogger(__name__)

MODEL_CODE_VERSION = "1.0.0"
FEATURES = ("latitude", "longitude", "area_sqft", "land_use", "price_basis", "observation_year", "observation_month")
CATEGORICAL = ("land_use", "price_basis")

# Below these the split is not informative enough to quote an error figure.
MIN_ROWS_TO_TRAIN = 40
MIN_HOLDOUT_ROWS = 10
MIN_DISTRICTS_FOR_GEOGRAPHIC_HOLDOUT = 4
MIN_MONTHS_FOR_TEMPORAL_HOLDOUT = 6
QUANTILE_LOW = 0.1
QUANTILE_HIGH = 0.9
# A range is only worth showing if it holds up out of sample. Below this share
# of its nominal coverage the interval is reported as not usable rather than
# dressed up as an "80% range" that in truth contains far less.
MIN_INTERVAL_COVERAGE_RATIO = 0.75


class TrainingError(RuntimeError):
    """Raised when a dataset cannot support an honestly evaluated model."""


@dataclass
class Metrics:
    """Held-out error for one model."""

    mae_inr_per_sqft: float
    rmse_inr_per_sqft: float
    median_absolute_percentage_error: float

    def as_dict(self) -> dict[str, float]:
        return {key: round(float(value), 2) for key, value in asdict(self).items()}


def _features(frame: pd.DataFrame) -> pd.DataFrame:
    out = frame.copy()
    out["observation_year"] = out["observation_date"].dt.year
    out["observation_month"] = out["observation_date"].dt.month
    return out.loc[:, list(FEATURES)]


def _metrics(actual: np.ndarray, predicted: np.ndarray) -> Metrics:
    error = predicted - actual
    return Metrics(
        mae_inr_per_sqft=float(np.mean(np.abs(error))),
        rmse_inr_per_sqft=float(np.sqrt(np.mean(error**2))),
        median_absolute_percentage_error=float(np.median(np.abs(error) / np.maximum(actual, 1e-9)) * 100.0),
    )


def choose_split(frame: pd.DataFrame) -> tuple[pd.Index, pd.Index, str, str]:
    """Pick the strongest holdout the dataset can actually support.

    Temporal is preferred: predicting the future from the past is the job. It
    needs a real time span, so a dataset crammed into a few months falls back to
    holding out whole districts, which at least tests unseen geography.
    """
    months = frame["observation_date"].dt.to_period("M").nunique()
    districts = frame["district"].str.casefold().nunique()

    if months >= MIN_MONTHS_FOR_TEMPORAL_HOLDOUT:
        cutoff = frame["observation_date"].quantile(0.8)
        train = frame.index[frame["observation_date"] <= cutoff]
        test = frame.index[frame["observation_date"] > cutoff]
        if len(test) >= MIN_HOLDOUT_ROWS and len(train) >= MIN_ROWS_TO_TRAIN:
            label = f"temporal: trained on or before {pd.Timestamp(cutoff).date()}, tested after"
            return train, test, "temporal", label

    if districts >= MIN_DISTRICTS_FOR_GEOGRAPHIC_HOLDOUT:
        # Hold out whole districts so no training row shares a district with a test row.
        ordered = frame["district"].str.casefold().value_counts().index.tolist()
        held_out = set(ordered[::4])
        mask = frame["district"].str.casefold().isin(held_out)
        train, test = frame.index[~mask], frame.index[mask]
        if len(test) >= MIN_HOLDOUT_ROWS and len(train) >= MIN_ROWS_TO_TRAIN:
            label = f"geographic: {len(held_out)} district(s) held out entirely"
            return train, test, "geographic", label

    raise TrainingError(
        "Dataset supports neither a temporal nor a geographic holdout "
        f"({len(frame)} rows, {months} distinct month(s), {districts} district(s)). "
        f"Need >= {MIN_MONTHS_FOR_TEMPORAL_HOLDOUT} months, or >= "
        f"{MIN_DISTRICTS_FOR_GEOGRAPHIC_HOLDOUT} districts, plus >= "
        f"{MIN_ROWS_TO_TRAIN} training and >= {MIN_HOLDOUT_ROWS} holdout rows."
    )


def _baseline_predictions(train: pd.DataFrame, test: pd.DataFrame) -> np.ndarray:
    """District median price per sqft, falling back to the global median."""
    medians = train.groupby(train["district"].str.casefold())["price_inr_per_sqft"].median()
    global_median = float(train["price_inr_per_sqft"].median())
    return test["district"].str.casefold().map(medians).fillna(global_median).to_numpy(dtype=float)


def _fit_regressor(
    features: pd.DataFrame,
    target: np.ndarray,
    encoder: OrdinalEncoder,
    **kwargs: Any,
) -> HistGradientBoostingRegressor:
    encoded = features.copy()
    encoded[list(CATEGORICAL)] = encoder.transform(features[list(CATEGORICAL)])
    model = HistGradientBoostingRegressor(
        max_iter=300,
        learning_rate=0.06,
        min_samples_leaf=5,
        categorical_features=[FEATURES.index(name) for name in CATEGORICAL],
        random_state=17,
        **kwargs,
    )
    model.fit(encoded.to_numpy(dtype=float), target)
    return model


def _predict(model: HistGradientBoostingRegressor, features: pd.DataFrame, encoder: OrdinalEncoder) -> np.ndarray:
    encoded = features.copy()
    encoded[list(CATEGORICAL)] = encoder.transform(features[list(CATEGORICAL)])
    return model.predict(encoded.to_numpy(dtype=float))


def train_model(csv_path: str | Path, output_path: str | Path, is_synthetic: bool = False) -> dict[str, Any]:
    """Import, split, train, evaluate and persist the valuation model."""
    frame, report = load_price_csv(csv_path)
    if len(frame) < MIN_ROWS_TO_TRAIN + MIN_HOLDOUT_ROWS:
        raise TrainingError(
            f"Only {len(frame)} usable rows after import; need at least "
            f"{MIN_ROWS_TO_TRAIN + MIN_HOLDOUT_ROWS}. Import report: {report.as_dict()}"
        )

    train_index, test_index, strategy, strategy_label = choose_split(frame)
    train_frame, test_frame = frame.loc[train_index], frame.loc[test_index]

    overlap = set(train_frame["property_key"]) & set(test_frame["property_key"])
    if overlap:
        raise TrainingError(
            f"{len(overlap)} property/properties appear in both halves of the split; "
            "the held-out error would be inflated by leakage."
        )

    target_train = train_frame["price_inr_per_sqft"].to_numpy(dtype=float)
    target_test = test_frame["price_inr_per_sqft"].to_numpy(dtype=float)
    features_train, features_test = _features(train_frame), _features(test_frame)

    encoder = OrdinalEncoder(handle_unknown="use_encoded_value", unknown_value=-1)
    encoder.fit(features_train[list(CATEGORICAL)])

    baseline_metrics = _metrics(target_test, _baseline_predictions(train_frame, test_frame))
    model = _fit_regressor(features_train, target_train, encoder)
    model_metrics = _metrics(target_test, _predict(model, features_test, encoder))

    # A prediction range is only reported because it is measured here.
    low_model = _fit_regressor(features_train, target_train, encoder, loss="quantile", quantile=QUANTILE_LOW)
    high_model = _fit_regressor(features_train, target_train, encoder, loss="quantile", quantile=QUANTILE_HIGH)
    low_test = _predict(low_model, features_test, encoder)
    high_test = _predict(high_model, features_test, encoder)
    interval_coverage = float(np.mean((target_test >= low_test) & (target_test <= high_test)) * 100.0)

    # Retrain on everything for serving; the metrics above stay those of the split.
    full_features, full_target = _features(frame), frame["price_inr_per_sqft"].to_numpy(dtype=float)
    full_encoder = OrdinalEncoder(handle_unknown="use_encoded_value", unknown_value=-1)
    full_encoder.fit(full_features[list(CATEGORICAL)])
    served = _fit_regressor(full_features, full_target, full_encoder)
    served_low = _fit_regressor(full_features, full_target, full_encoder, loss="quantile", quantile=QUANTILE_LOW)
    served_high = _fit_regressor(full_features, full_target, full_encoder, loss="quantile", quantile=QUANTILE_HIGH)

    data_version = dataset_version(frame)
    metadata: dict[str, Any] = {
        "model_version": f"{MODEL_CODE_VERSION}+{data_version}",
        "model_code_version": MODEL_CODE_VERSION,
        "data_version": data_version,
        "trained_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "is_synthetic": bool(is_synthetic),
        "source_csv": Path(csv_path).name,
        "import_report": report.as_dict(),
        "validation": {
            "strategy": strategy,
            "description": strategy_label,
            "train_rows": int(len(train_frame)),
            "holdout_rows": int(len(test_frame)),
            "baseline": baseline_metrics.as_dict(),
            "model": model_metrics.as_dict(),
            "model_beats_baseline": bool(model_metrics.mae_inr_per_sqft < baseline_metrics.mae_inr_per_sqft),
            "interval": {
                "lower_quantile": QUANTILE_LOW,
                "upper_quantile": QUANTILE_HIGH,
                "measured_holdout_coverage_pct": round(interval_coverage, 1),
                "nominal_coverage_pct": round((QUANTILE_HIGH - QUANTILE_LOW) * 100, 1),
                "reportable": bool(
                    interval_coverage
                    >= MIN_INTERVAL_COVERAGE_RATIO * (QUANTILE_HIGH - QUANTILE_LOW) * 100
                ),
            },
        },
        "coverage": {
            "rows": int(len(frame)),
            "districts": sorted(frame["district"].dropna().unique().tolist()),
            "states": sorted(frame["state"].dropna().unique().tolist()),
            "land_uses": sorted(frame["land_use"].unique().tolist()),
            "price_basis_counts": {str(k): int(v) for k, v in frame["price_basis"].value_counts().items()},
            "observation_date_from": frame["observation_date"].min().date().isoformat(),
            "observation_date_to": frame["observation_date"].max().date().isoformat(),
            "area_sqft_p05": round(float(frame["area_sqft"].quantile(0.05)), 2),
            "area_sqft_p95": round(float(frame["area_sqft"].quantile(0.95)), 2),
        },
    }

    import joblib

    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(
        {
            "metadata": metadata,
            "encoder": full_encoder,
            "model": served,
            "low_model": served_low,
            "high_model": served_high,
            # Retained for the support check and the district baseline at serve time.
            "reference_points": frame[
                ["latitude", "longitude", "district", "state", "land_use", "price_inr_per_sqft"]
            ].to_dict("records"),
        },
        output,
    )
    output.with_suffix(".metadata.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    LOGGER.info("Wrote valuation model %s (%s)", output, metadata["model_version"])
    return metadata


def default_model_path() -> Path:
    return Path(os.getenv("VALUATION_MODEL_PATH", str(Path(__file__).parent / "artifacts" / "land_price_model.joblib")))


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Train the TerraScope land valuation model.")
    parser.add_argument("csv", help="Land-price CSV following valuation/README.md")
    parser.add_argument("--out", default=str(default_model_path()), help="Output .joblib path")
    parser.add_argument(
        "--synthetic",
        action="store_true",
        help="Mark the artifact as synthetic; predictions are then flagged demo-only.",
    )
    arguments = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    result = train_model(arguments.csv, arguments.out, is_synthetic=arguments.synthetic)
    print(json.dumps(result["validation"], indent=2))
