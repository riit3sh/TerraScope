"""Comparable-property baseline: a transparent price range from similar nearby land.

Comparables must share the price type, land use and land category, sit close to
the parcel (the smallest radius that yields enough of them), be recent, and be of
similar size. The result is the comparables' own spread. It is reported as such,
never as a statistically validated prediction interval.
"""

from __future__ import annotations

from datetime import date
from typing import Any

import numpy as np
import pandas as pd

from .dataset import COMPARABLE_PRECISIONS, PRICE_TYPE_LABELS, PRICE_TYPES, LAND_USES, haversine_m

MIN_COMPARABLES = 5
RADII_KM = (1.0, 2.0, 5.0, 10.0)
# A comparable may be at most this many times larger or smaller than the parcel:
# a 2,400 sq ft plot says nothing about a 60-acre campus or farm.
MAX_AREA_RATIO = 3.0
MAX_AGE_DAYS = {"asking": 548, "transaction": 1096, "guideline": 1096}  # 18 months; 3 years
WIDE_SPREAD = 0.5  # interquartile range / median


class ValuationUnavailable(Exception):
    def __init__(self, reason: str, detail: str) -> None:
        super().__init__(detail)
        self.reason = reason
        self.detail = detail


def category_for(land_use: str) -> str:
    return "agricultural_land" if land_use == "agricultural" else "vacant_plot"


def _inr(value: float) -> str:
    return f"₹{value:,.0f}"


def estimate(
    observations: pd.DataFrame,
    *,
    latitude: float,
    longitude: float,
    area_sqft: float,
    land_use: str,
    price_type: str = "asking",
    valuation_date: date,
) -> dict[str, Any]:
    """Estimate ₹/sq ft from comparables in ``observations``, or raise ValuationUnavailable."""
    if price_type not in PRICE_TYPES:
        raise ValuationUnavailable("invalid_input", f"price_type must be one of {list(PRICE_TYPES)}.")
    if land_use not in LAND_USES:
        raise ValuationUnavailable("invalid_input", f"land_use must be one of {list(LAND_USES)}.")
    label = PRICE_TYPE_LABELS[price_type]
    pool = observations[observations["price_type"] == price_type]
    if pool.empty:
        short = {"asking": "asking prices", "transaction": "registered sale prices", "guideline": "guideline values"}
        raise ValuationUnavailable("price_type_not_covered", f"No {short[price_type]} are loaded.")
    category = category_for(land_use)
    pool = pool[(pool["land_use"] == land_use) & (pool["property_category"] == category)]
    if pool.empty:
        raise ValuationUnavailable(
            "land_use_not_covered", f"No {land_use.replace('_', ' ')} {category.replace('_', ' ')} observations are loaded.")
    pool = pool[pool["location_precision"].isin(COMPARABLE_PRECISIONS)]
    when = pd.Timestamp(valuation_date)
    # Never look into the future of the valuation date (this also keeps holdout tests honest).
    pool = pool[pool["observed_date"] <= when]
    distance_km = pd.Series(haversine_m(latitude, longitude, pool["latitude"].to_numpy(), pool["longitude"].to_numpy()) / 1000,
                            index=pool.index)
    near = pool[distance_km <= RADII_KM[-1]]
    if near.empty:
        nearest = f"{distance_km.min():,.1f} km" if len(distance_km) else "none"
        raise ValuationUnavailable(
            "no_comparables_nearby",
            f"No {label} for {land_use.replace('_', ' ')} land within {RADII_KM[-1]:.0f} km (nearest: {nearest}).")
    fresh = near[(when - near["observed_date"]).dt.days <= MAX_AGE_DAYS[price_type]]
    if fresh.empty:
        raise ValuationUnavailable(
            "stale_data_only",
            f"{len(near)} observation(s) lie within {RADII_KM[-1]:.0f} km, but all are older than "
            f"{MAX_AGE_DAYS[price_type] // 30} months (latest {near['observed_date'].max().date()}).")
    sized = fresh[fresh["area_sqft"].between(area_sqft / MAX_AREA_RATIO, area_sqft * MAX_AREA_RATIO)]
    if price_type == "guideline":
        sized = pd.concat([sized, fresh[fresh["area_sqft"].isna()]])  # rates per unit, no plot size
    if sized.empty:
        low, high = fresh["area_sqft"].min(), fresh["area_sqft"].max()
        raise ValuationUnavailable(
            "area_outside_support",
            f"The {len(fresh)} nearby comparables are {low:,.0f}-{high:,.0f} sq ft; this parcel is {area_sqft:,.0f} sq ft. "
            f"Prices per sq ft do not transfer across that difference in size, so no estimate is given.")
    for radius in RADII_KM:
        chosen = sized[distance_km[sized.index] <= radius]
        if len(chosen) >= MIN_COMPARABLES:
            break
    else:
        raise ValuationUnavailable(
            "insufficient_comparables",
            f"Only {len(sized)} comparable {label} of similar size within {RADII_KM[-1]:.0f} km; "
            f"at least {MIN_COMPARABLES} are needed.")

    prices = chosen["price_inr_per_sqft"].to_numpy(dtype=float)
    median = float(np.median(prices))
    p25, p75 = (float(v) for v in np.percentile(prices, [25, 75]))
    ages = (when - chosen["observed_date"]).dt.days
    areas = chosen["area_sqft"].dropna()
    within_sizes = bool(len(areas)) and areas.min() <= area_sqft <= areas.max()

    reasons = []
    if price_type == "asking":
        reasons.append("Asking prices are what sellers request; completed sales commonly differ from them.")
    if price_type == "guideline":
        reasons.append("Guideline values are administrative floors for stamp duty, not market prices.")
    if len(chosen) < 2 * MIN_COMPARABLES:
        reasons.append(f"Only {len(chosen)} comparables.")
    if p75 - p25 > WIDE_SPREAD * median:
        reasons.append(f"Comparables disagree widely: the middle half spans {_inr(p25)}-{_inr(p75)} per sq ft.")
    if radius > 2:
        reasons.append(f"Comparables had to be drawn from up to {radius:.0f} km away.")
    if float(ages.median()) > 365:
        reasons.append("Most comparables are more than a year old; prices are not adjusted for time.")
    coarse = int((chosen["location_precision"] == "locality").sum())
    if coarse:
        reasons.append(f"{coarse} comparable(s) are located only to a locality, not to the plot.")
    if not within_sizes:
        reasons.append("The parcel is outside the comparables' size range, so no total value is given.")
    reasons.append("Plot-specific facts (road frontage, shape, approvals, title) are not known and not adjusted for.")

    order = distance_km[chosen.index].sort_values().index
    comparables = [
        {
            "source": row["source"], "source_record_id": row["source_record_id"], "source_url": row["source_url"] or None,
            "reuse_basis": row["reuse_basis"], "price_type": row["price_type"],
            "observed_date": row["observed_date"].date().isoformat(), "retrieved_date": row["retrieved_date"].date().isoformat(),
            "price_inr_per_sqft": round(float(row["price_inr_per_sqft"]), 2),
            "area_sqft": None if pd.isna(row["area_sqft"]) else round(float(row["area_sqft"]), 1),
            "distance_km": round(float(distance_km[index]), 2), "location_precision": row["location_precision"],
            "locality": row["locality"] or None, "listed_by_sources": int(row["group_size"]),
        }
        for index, row in chosen.loc[order].iterrows()
    ]
    return {
        "status": "available",
        "method": "comparable_median",
        "price_type": price_type,
        "price_type_label": label,
        "land_use": land_use,
        "property_category": category,
        "area_sqft": round(float(area_sqft), 1),
        "valuation_date": when.date().isoformat(),
        "estimate_inr_per_sqft": round(median, 2),
        "spread_inr_per_sqft": {"p25": round(p25, 2), "p75": round(p75, 2),
                                "min": round(float(prices.min()), 2), "max": round(float(prices.max()), 2)},
        "spread_basis": (
            "Middle half (25th-75th percentile) of the comparables' own prices. This is the spread of "
            "similar observations, not a statistically validated prediction interval."
        ),
        "total_inr": None if not within_sizes else {
            "estimate": round(median * area_sqft), "p25": round(p25 * area_sqft), "p75": round(p75 * area_sqft)},
        "comparable_count": len(chosen),
        "radius_km": radius,
        "observed_from": chosen["observed_date"].min().date().isoformat(),
        "observed_to": chosen["observed_date"].max().date().isoformat(),
        "sources": sorted(chosen["source"].unique().tolist()),
        "uncertainty": reasons,
        "comparables": comparables[:15],
    }
