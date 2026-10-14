"""Land-cover change from dated NDVI/NDBI observations, compared season against season.

Method ``seasonal_pairs_v2``: each observation is paired with one about a year earlier
from the same season (day of year within 45 days, 300-430 days apart), so monsoon greening
is never mistaken for change. The paired differences are then read with fixed rule
thresholds:

* every pair within +/-STABLE_LIMIT on both indices -> ``no_change``;
* every pair moving the same way by at least STABLE_LIMIT, median at least CHANGE_LIMIT ->
  ``construction_growth`` (NDVI down, NDBI up), ``vegetation_loss`` or ``vegetation_gain``;
* anything else, or fewer than MIN_PAIRS pairs -> ``inconclusive``.

No confidence figure is produced: the thresholds are rules, not calibrated against labelled
change, so a percentage would claim a probability nobody has measured. It replaces
``statistical_change_v1`` (a linear trend whose "confidence" was half the mean R2, and which
filed ambiguous movement under "no change").
"""

from __future__ import annotations

from datetime import date
from statistics import median
from typing import Any


METHOD = "seasonal_pairs_v2"
PAIR_GAP_DAYS = (300, 430)
MAX_SEASON_OFFSET_DAYS = 45
STABLE_LIMIT = 0.05
CHANGE_LIMIT = 0.10
MIN_PAIRS = 2


def _day(value: Any) -> date:
    return date.fromisoformat(str(value)[:10])


def seasonal_pairs(series: list[dict[str, Any]]) -> list[tuple[dict[str, Any], dict[str, Any]]]:
    """(earlier, later) observations about a year apart in the same season; each used once."""
    rows = sorted(series, key=lambda row: _day(row["date"]))
    used: set[int] = set()
    pairs = []
    for j, later in enumerate(rows):
        best = None
        for i, earlier in enumerate(rows[:j]):
            if i in used:
                continue
            gap = (_day(later["date"]) - _day(earlier["date"])).days
            season = abs(_day(later["date"]).timetuple().tm_yday - _day(earlier["date"]).timetuple().tm_yday)
            season = min(season, 365 - season)
            if PAIR_GAP_DAYS[0] <= gap <= PAIR_GAP_DAYS[1] and season <= MAX_SEASON_OFFSET_DAYS:
                if best is None or abs(gap - 365) < abs((_day(later["date"]) - _day(rows[best]["date"])).days - 365):
                    best = i
        if best is not None:
            used.add(best)
            used.add(j)
            pairs.append((rows[best], later))
    return pairs


def _direction(changes: list[float]) -> int:
    """+1 / -1 when every pair moved that way by at least STABLE_LIMIT and the median by CHANGE_LIMIT."""
    if all(c >= STABLE_LIMIT for c in changes) and median(changes) >= CHANGE_LIMIT:
        return 1
    if all(c <= -STABLE_LIMIT for c in changes) and median(changes) <= -CHANGE_LIMIT:
        return -1
    return 0


def detect_change_from_series(ndvi_ndbi_series: list[dict[str, Any]]) -> dict[str, Any]:
    usable = [
        row for row in ndvi_ndbi_series or []
        if isinstance(row, dict) and row.get("date") and row.get("ndvi") is not None and row.get("ndbi") is not None
    ]
    method: dict[str, Any] = {
        "method": METHOD, "observations": len(usable), "pairs": 0,
        "stable_limit": STABLE_LIMIT, "change_limit": CHANGE_LIMIT, "calibrated": False,
    }
    if len(usable) < 2:
        method["reason"] = "Fewer than two usable observations."
        return {"change_detected": None, "change_type": "insufficient_evidence", "change_confidence": None,
                "change_method": method}

    pairs = seasonal_pairs(usable)
    ndvi = [round(later["ndvi"] - earlier["ndvi"], 4) for earlier, later in pairs]
    ndbi = [round(later["ndbi"] - earlier["ndbi"], 4) for earlier, later in pairs]
    method.update({
        "pairs": len(pairs),
        "pair_dates": [[earlier["date"], later["date"]] for earlier, later in pairs],
        "ndvi_changes": ndvi,
        "ndbi_changes": ndbi,
        "median_ndvi_change": round(median(ndvi), 4) if ndvi else None,
        "median_ndbi_change": round(median(ndbi), 4) if ndbi else None,
    })
    if len(pairs) < MIN_PAIRS:
        method["reason"] = (
            f"Only {len(pairs)} same-season pair(s) a year apart; at least {MIN_PAIRS} are needed to tell change "
            "from seasonal and atmospheric variation."
        )
        return {"change_detected": None, "change_type": "inconclusive", "change_confidence": None,
                "change_method": method}

    ndvi_way, ndbi_way = _direction(ndvi), _direction(ndbi)
    if all(abs(c) < STABLE_LIMIT for c in ndvi + ndbi):
        change_type, reason = "no_change", (
            f"Every same-season pair changed by less than {STABLE_LIMIT} in both NDVI and NDBI.")
    elif ndvi_way < 0 and ndbi_way > 0:
        change_type, reason = "construction_growth", "NDVI fell and NDBI rose consistently in every pair."
    elif ndvi_way < 0:
        change_type, reason = "vegetation_loss", "NDVI fell consistently in every pair."
    elif ndvi_way > 0 and ndbi_way <= 0:
        change_type, reason = "vegetation_gain", "NDVI rose consistently in every pair."
    else:
        change_type, reason = "inconclusive", (
            f"Pairs disagree or move by less than the {CHANGE_LIMIT} change threshold, but not all stay within "
            f"+/-{STABLE_LIMIT}; the signal does not support either 'no change' or a change class.")
    method["reason"] = reason
    return {
        "change_detected": None if change_type == "inconclusive" else change_type != "no_change",
        "change_type": change_type,
        "change_confidence": None,
        "change_method": method,
    }
