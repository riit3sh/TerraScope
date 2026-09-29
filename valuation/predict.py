"""Serve land valuations, or refuse them explicitly.

A refusal is a first-class result here. Returning a confident number for a
location the training data never covered would be worse than returning nothing,
so every prediction states the evidence standing behind it.
"""

from __future__ import annotations

import logging
import math
import os
import threading
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from .dataset import LAND_USES
from .train import CATEGORICAL, FEATURES, default_model_path


LOGGER = logging.getLogger(__name__)

# A parcel must sit near enough to real observations for the model to mean anything.
MAX_SUPPORT_DISTANCE_KM = float(os.getenv("VALUATION_MAX_SUPPORT_DISTANCE_KM", "25"))
MIN_SUPPORTING_OBSERVATIONS = int(os.getenv("VALUATION_MIN_SUPPORTING_OBSERVATIONS", "5"))

_CACHE: dict[str, Any] = {}
_LOCK = threading.Lock()


def synthetic_allowed() -> bool:
    """Demo mode: whether a model trained on the synthetic fixture may quote prices.

    Read per call, not at import, so it can be toggled without a restart in tests.
    """
    return os.getenv("VALUATION_ALLOW_SYNTHETIC", "").strip().lower() in {"1", "true", "yes"}


class ValuationUnavailable(Exception):
    """Raised when no defensible estimate can be produced."""

    def __init__(self, reason: str, detail: str) -> None:
        super().__init__(detail)
        self.reason = reason
        self.detail = detail


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    radius = 6371.0088
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    d_phi = phi2 - phi1
    d_lambda = math.radians(lon2 - lon1)
    a = math.sin(d_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    return 2 * radius * math.asin(math.sqrt(a))


def load_artifact(path: str | Path | None = None) -> dict[str, Any]:
    """Load and memoize the trained artifact; raises if none has been trained."""
    target = Path(path) if path else default_model_path()
    key = str(target.resolve()) if target.exists() else str(target)
    with _LOCK:
        cached = _CACHE.get(key)
        stamp = target.stat().st_mtime if target.exists() else None
        if cached and cached.get("stamp") == stamp:
            return cached["artifact"]
        if not target.exists():
            raise ValuationUnavailable(
                "model_not_trained",
                f"No valuation model artifact at {target}. Train one with "
                "`python -m valuation.train <price_csv>` (see valuation/README.md).",
            )
        import joblib

        artifact = joblib.load(target)
        _CACHE[key] = {"stamp": stamp, "artifact": artifact}
        return artifact


def model_status(path: str | Path | None = None) -> dict[str, Any]:
    """Describe the currently served model without making a prediction."""
    try:
        artifact = load_artifact(path)
    except ValuationUnavailable as error:
        return {"available": False, "reason": error.reason, "detail": error.detail}
    metadata = artifact["metadata"]
    return {
        "available": True,
        "model_version": metadata["model_version"],
        "data_version": metadata["data_version"],
        "trained_at": metadata["trained_at"],
        "is_synthetic": metadata["is_synthetic"],
        "validation": metadata["validation"],
        "coverage": metadata["coverage"],
    }


def _support(artifact: dict[str, Any], latitude: float, longitude: float) -> dict[str, Any]:
    """How much observed evidence sits near this parcel."""
    distances = [
        (_haversine_km(latitude, longitude, float(point["latitude"]), float(point["longitude"])), point)
        for point in artifact["reference_points"]
    ]
    distances.sort(key=lambda item: item[0])
    nearby = [(distance, point) for distance, point in distances if distance <= MAX_SUPPORT_DISTANCE_KM]
    return {
        "nearest_observation_km": round(distances[0][0], 2) if distances else None,
        "observations_within_radius": len(nearby),
        "radius_km": MAX_SUPPORT_DISTANCE_KM,
        "districts_nearby": sorted({str(point["district"]) for _, point in nearby if point.get("district")}),
        "nearby": nearby,
    }


def estimate_value(
    latitude: float,
    longitude: float,
    area_sqft: float,
    land_use: str = "residential",
    price_basis: str = "transaction",
    valuation_date: date | None = None,
    model_path: str | Path | None = None,
) -> dict[str, Any]:
    """Estimate INR/sqft and total value, or raise ValuationUnavailable."""
    if not (-90 <= latitude <= 90) or not (-180 <= longitude <= 180):
        raise ValuationUnavailable("invalid_input", "Latitude/longitude are out of range.")
    if not isinstance(area_sqft, (int, float)) or area_sqft <= 0:
        raise ValuationUnavailable("invalid_input", "Area must be a positive number of square feet.")
    normalized_use = str(land_use or "residential").strip().lower()
    if normalized_use not in LAND_USES:
        raise ValuationUnavailable(
            "unsupported_land_use",
            f"Land use {land_use!r} is not one of {list(LAND_USES)}.",
        )

    artifact = load_artifact(model_path)
    metadata = artifact["metadata"]
    if metadata["is_synthetic"] and not synthetic_allowed():
        raise ValuationUnavailable(
            "synthetic_model_only",
            (
                "The only trained valuation model was fitted on synthetic demo rows, not real "
                "market prices, so no price is quoted. Train on a real price CSV with "
                "`python -m valuation.train <csv>`, or set VALUATION_ALLOW_SYNTHETIC=true "
                "to show clearly labelled demo figures."
            ),
        )
    support = _support(artifact, latitude, longitude)

    if support["observations_within_radius"] < MIN_SUPPORTING_OBSERVATIONS:
        nearest = support["nearest_observation_km"]
        raise ValuationUnavailable(
            "location_not_covered",
            (
                f"Only {support['observations_within_radius']} training observation(s) lie within "
                f"{MAX_SUPPORT_DISTANCE_KM:.0f} km of this parcel (nearest "
                f"{'none' if nearest is None else f'{nearest} km'} away); "
                f"at least {MIN_SUPPORTING_OBSERVATIONS} are required. "
                f"The dataset covers: {', '.join(metadata['coverage']['districts']) or 'no districts'}."
            ),
        )
    if normalized_use not in metadata["coverage"]["land_uses"]:
        raise ValuationUnavailable(
            "land_use_not_covered",
            f"The dataset contains no {normalized_use} rows; it covers {metadata['coverage']['land_uses']}.",
        )

    when = valuation_date or datetime.now(timezone.utc).date()
    features = pd.DataFrame(
        [
            {
                "latitude": float(latitude),
                "longitude": float(longitude),
                "area_sqft": float(area_sqft),
                "land_use": normalized_use,
                "price_basis": str(price_basis or "transaction").strip().lower(),
                "observation_year": when.year,
                "observation_month": when.month,
            }
        ]
    ).loc[:, list(FEATURES)]

    encoder = artifact["encoder"]
    encoded = features.copy()
    encoded[list(CATEGORICAL)] = encoder.transform(features[list(CATEGORICAL)])
    matrix = encoded.to_numpy(dtype=float)

    per_sqft = float(artifact["model"].predict(matrix)[0])
    low = float(artifact["low_model"].predict(matrix)[0])
    high = float(artifact["high_model"].predict(matrix)[0])
    if per_sqft <= 0:
        raise ValuationUnavailable(
            "non_positive_estimate",
            "The model produced a non-positive price per sqft; refusing to report it.",
        )
    low, high = max(1.0, min(low, per_sqft)), max(high, per_sqft)

    interval = metadata["validation"]["interval"]
    # Only surface a range that earned it on the holdout.
    if interval.get("reportable"):
        value_range: dict[str, Any] | None = {
            "low_inr_per_sqft": round(low, 2),
            "high_inr_per_sqft": round(high, 2),
            "low_total_inr": round(low * float(area_sqft), 2),
            "high_total_inr": round(high * float(area_sqft), 2),
            "nominal_coverage_pct": interval["nominal_coverage_pct"],
            "measured_holdout_coverage_pct": interval["measured_holdout_coverage_pct"],
            "basis": (
                f"Quantile regression at {interval['lower_quantile']}/{interval['upper_quantile']}; "
                f"contained {interval['measured_holdout_coverage_pct']}% of held-out prices."
            ),
        }
        range_unavailable_reason = None
    else:
        value_range = None
        range_unavailable_reason = (
            f"The {interval['nominal_coverage_pct']}% interval contained only "
            f"{interval['measured_holdout_coverage_pct']}% of held-out prices, so no range is shown."
        )
    return {
        "status": "available",
        "estimated_inr_per_sqft": round(per_sqft, 2),
        "estimated_total_inr": round(per_sqft * float(area_sqft), 2),
        "area_sqft": round(float(area_sqft), 2),
        "range": value_range,
        "range_unavailable_reason": range_unavailable_reason,
        "land_use": normalized_use,
        "valuation_date": when.isoformat(),
        "model_version": metadata["model_version"],
        "data_version": metadata["data_version"],
        "trained_at": metadata["trained_at"],
        "is_synthetic": metadata["is_synthetic"],
        "accuracy": {
            "holdout_strategy": metadata["validation"]["strategy"],
            "holdout_description": metadata["validation"]["description"],
            "model_mae_inr_per_sqft": metadata["validation"]["model"]["mae_inr_per_sqft"],
            "model_rmse_inr_per_sqft": metadata["validation"]["model"]["rmse_inr_per_sqft"],
            "baseline_mae_inr_per_sqft": metadata["validation"]["baseline"]["mae_inr_per_sqft"],
            "baseline_rmse_inr_per_sqft": metadata["validation"]["baseline"]["rmse_inr_per_sqft"],
            "model_beats_baseline": metadata["validation"]["model_beats_baseline"],
        },
        "evidence_coverage": {
            "nearest_observation_km": support["nearest_observation_km"],
            "observations_within_radius": support["observations_within_radius"],
            "radius_km": support["radius_km"],
            "districts_nearby": support["districts_nearby"],
            "dataset_rows": metadata["coverage"]["rows"],
            "dataset_date_from": metadata["coverage"]["observation_date_from"],
            "dataset_date_to": metadata["coverage"]["observation_date_to"],
            "price_basis_counts": metadata["coverage"]["price_basis_counts"],
        },
    }
