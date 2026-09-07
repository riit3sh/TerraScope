"""Simple NDVI/NDBI time-series change detection for Review 2."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

import numpy as np


NOISE_THRESHOLD_PER_30_DAYS = 0.02


def _parse_date(value: str | date | datetime) -> datetime:
    if isinstance(value, datetime):
        return value
    if isinstance(value, date):
        return datetime.combine(value, datetime.min.time())
    return datetime.fromisoformat(str(value).replace("Z", "+00:00")).replace(tzinfo=None)


def _fit_trend(series: list[dict[str, Any]], field: str) -> tuple[float, float]:
    dates = [_parse_date(item["date"]) for item in series]
    values = np.asarray([float(item[field]) for item in series], dtype=float)
    elapsed_days = np.asarray([(item - dates[0]).total_seconds() / 86_400 for item in dates], dtype=float)
    if len(values) < 2 or not np.isfinite(values).all():
        return 0.0, 0.0

    slope_per_day, intercept = np.polyfit(elapsed_days, values, 1)
    predicted = slope_per_day * elapsed_days + intercept
    residual_sum_squares = float(np.sum((values - predicted) ** 2))
    total_sum_squares = float(np.sum((values - np.mean(values)) ** 2))
    r_squared = 0.0 if total_sum_squares <= 1e-12 else 1.0 - residual_sum_squares / total_sum_squares
    return float(slope_per_day * 30.0), float(np.clip(r_squared, 0.0, 1.0))


def detect_change_from_series(ndvi_ndbi_series: list[dict[str, Any]]) -> dict[str, Any]:
    """Classify change from dated NDVI/NDBI observations using linear trends.

    Slopes are normalized to change per 30 days so the threshold is stable
    across daily, weekly, and monthly acquisition intervals. Missing or
    insufficient observations are treated as insufficient evidence and map to
    the conservative ``no_change`` result for this narrow Review 2 tier.
    """
    if not ndvi_ndbi_series:
        return {"change_detected": False, "change_type": "no_change", "change_confidence": 0.0}

    usable = [
        item for item in ndvi_ndbi_series
        if isinstance(item, dict) and item.get("date") is not None and item.get("ndvi") is not None and item.get("ndbi") is not None
    ]
    if len(usable) < 2:
        return {"change_detected": False, "change_type": "no_change", "change_confidence": 0.0}
    usable = sorted(usable, key=lambda item: _parse_date(item["date"]))

    ndvi_slope, ndvi_r2 = _fit_trend(usable, "ndvi")
    ndbi_slope, ndbi_r2 = _fit_trend(usable, "ndbi")
    threshold = NOISE_THRESHOLD_PER_30_DAYS
    ndvi_falling = ndvi_slope <= -threshold
    ndbi_rising = ndbi_slope >= threshold
    ndbi_flat = abs(ndbi_slope) < threshold
    ndvi_flat = abs(ndvi_slope) < threshold

    if ndbi_rising and ndvi_falling:
        change_type = "construction_growth"
    elif ndvi_falling and ndbi_flat:
        change_type = "vegetation_loss"
    elif ndvi_flat and ndbi_flat:
        change_type = "no_change"
    else:
        # Ambiguous movement is intentionally conservative until richer labels exist.
        change_type = "no_change"

    mean_r2 = (ndvi_r2 + ndbi_r2) / 2.0
    if change_type == "no_change":
        confidence = mean_r2 * 0.5
    else:
        trend_strength = min(1.0, max(abs(ndvi_slope), abs(ndbi_slope)) / (threshold * 2.0))
        confidence = mean_r2 * trend_strength
    return {
        "change_detected": change_type != "no_change",
        "change_type": change_type,
        "change_confidence": round(float(np.clip(confidence, 0.0, 1.0)), 3),
    }


# A labeled-training-data CNN is a documented next step, not attempted in this Review 2 tier.

