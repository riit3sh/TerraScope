"""Serve listing-based price ranges, or refuse them explicitly.

The served data is a CSV of price observations (dataset.py contract) at
VALUATION_OBSERVATIONS_PATH, default data-cache/valuation/observations.csv. It is
git-ignored: it holds licensed or permissioned data. No file means no estimate.
"""

from __future__ import annotations

import json
import os
import threading
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from .comparables import ValuationUnavailable, estimate
from .dataset import LAND_USES, PRICE_TYPES, DatasetError, dataset_version, load_observations, summary

_CACHE: dict[str, Any] = {}
_LOCK = threading.Lock()


def observations_path() -> Path:
    configured = os.getenv("VALUATION_OBSERVATIONS_PATH")
    if configured:
        return Path(configured)
    root = os.getenv("TERRASCOPE_DATA_DIR") or str(Path(__file__).resolve().parents[1] / "data-cache")
    return Path(root) / "valuation" / "observations.csv"


def _store() -> dict[str, Any]:
    """Cleaned observations, reloaded only when the file changes."""
    path = observations_path()
    if not path.exists():
        raise ValuationUnavailable(
            "no_price_data",
            "No land-price observations are loaded, so no price is estimated. TerraScope has no licensed listing "
            "feed or permitted transaction data yet.",
        )
    stamp = path.stat().st_mtime
    with _LOCK:
        if _CACHE.get("path") == str(path) and _CACHE.get("stamp") == stamp:
            return _CACHE
        try:
            frame, report = load_observations(path)
        except DatasetError as error:
            raise ValuationUnavailable("price_data_invalid", f"The price observations could not be used: {error}") from error
        quality = {}
        for price_type in ("asking", "transaction", "guideline"):
            report_path = Path(f"{path}.quality-{price_type}.json")
            if report_path.exists():
                quality[price_type] = json.loads(report_path.read_text(encoding="utf-8"))
        _CACHE.clear()
        _CACHE.update(path=str(path), stamp=stamp, frame=frame, report=report.as_dict(),
                      version=dataset_version(frame), summary=summary(frame), quality=quality)
        return _CACHE


def data_status() -> dict[str, Any]:
    try:
        store = _store()
    except ValuationUnavailable as error:
        return {"available": False, "reason": error.reason, "detail": error.detail}
    return {"available": True, "data_version": store["version"], "import": store["report"], "data": store["summary"],
            "validation": {k: v.get("status") for k, v in store["quality"].items()}}


def estimate_value(
    latitude: float,
    longitude: float,
    area_sqft: float,
    land_use: str = "residential",
    price_basis: str = "asking",
    valuation_date: date | None = None,
) -> dict[str, Any]:
    """Comparable-based estimate for one parcel, or raise ValuationUnavailable."""
    if not (-90 <= latitude <= 90) or not (-180 <= longitude <= 180):
        raise ValuationUnavailable("invalid_input", "Latitude/longitude are out of range.")
    if not area_sqft or area_sqft <= 0:
        raise ValuationUnavailable("invalid_input", "Area must be a positive number of square feet.")
    land_use, price_type = str(land_use).strip().lower(), str(price_basis).strip().lower()
    # A bad request is a bad request whether or not any price data is loaded.
    if land_use not in LAND_USES or price_type not in PRICE_TYPES:
        raise ValuationUnavailable("invalid_input", f"land_use must be one of {list(LAND_USES)} and "
                                                    f"price_basis one of {list(PRICE_TYPES)}.")
    store = _store()
    when = valuation_date or datetime.now(timezone.utc).date()
    result = estimate(store["frame"], latitude=latitude, longitude=longitude, area_sqft=float(area_sqft),
                      land_use=land_use, price_type=price_type, valuation_date=when)
    quality = store["quality"].get(result["price_type"])
    result["data_version"] = store["version"]
    # The prediction-quality report travels with every estimate: "not yet validated"
    # is part of the answer, not a footnote.
    result["validation"] = (
        {"status": quality.get("status"), "holdouts": {
            name: {key: h.get(key) for key in ("estimates", "prediction_coverage_pct", "status", "baseline")}
            for name, h in quality.get("holdouts", {}).items()}}
        if quality else {"status": "not_yet_validated", "note": "No held-out evaluation has been run on this data."}
    )
    return result
