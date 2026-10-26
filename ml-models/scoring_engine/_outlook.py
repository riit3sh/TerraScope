"""Development outlook: the 2017-2023 built-up trend around the plot, projected forward with its uncertainty.

A straight-line fit through the seven annual land-cover values within 1 km (the same series the growth factor uses),
extended to the given years with a 95 % prediction interval. It projects building on the ground only: not prices,
not approvals, and not events the past cannot show (a new highway, a policy change, a flood). The share is capped at
100 %, and an area already over 85 % built is called built out rather than growing.
"""

from __future__ import annotations

import math
from typing import Any

PROJECT_TO = (2026, 2030)
T_975 = {3: 3.182, 4: 2.776, 5: 2.571, 6: 2.447, 7: 2.365, 8: 2.306}  # Student t, two-sided 95 %, by degrees of freedom
DISCLAIMER = ("A projection of the 2017-2023 trend, not a prediction of prices or a guarantee: new roads, policy, "
              "markets or disasters can change it. The range shows how far the past years already scattered.")


def development_outlook(record: dict[str, Any]) -> dict[str, Any]:
    history = record.get("land_cover_history") if isinstance(record.get("land_cover_history"), dict) else {}
    points = [(p["year"], p["built_share_within_1km"]) for p in history.get("surroundings") or []
              if isinstance(p, dict) and isinstance(p.get("built_share_within_1km"), (int, float))]
    if len(points) < 5:
        return {"status": "unavailable", "reason": "fewer than five years of land-cover history", "disclaimer": DISCLAIMER}
    n = len(points)
    xs, ys = [x for x, _ in points], [y for _, y in points]
    mx, my = sum(xs) / n, sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    slope = sum((x - mx) * (y - my) for x, y in points) / sxx
    intercept = my - slope * mx
    residual = math.sqrt(sum((y - (intercept + slope * x)) ** 2 for x, y in points) / (n - 2))
    t = T_975.get(n - 2, 2.0)
    projections = []
    for year in PROJECT_TO:
        centre = intercept + slope * year
        half = t * residual * math.sqrt(1 + 1 / n + (year - mx) ** 2 / sxx)
        clamp = lambda v: round(max(0.0, min(1.0, v)), 4)  # noqa: E731
        projections.append({"year": year, "share": clamp(centre), "low": clamp(centre - half), "high": clamp(centre + half)})
    last = ys[-1]
    status = ("built_out" if last >= 0.85 else "growing_fast" if slope * 100 >= 1.0 else
              "growing_slowly" if slope * 100 >= 0.3 else "flat")
    return {"status": status, "slope_pts_per_year": round(slope * 100, 2), "from_year": xs[0], "to_year": xs[-1],
            "last_share": round(last, 4), "projections": projections, "method": "linear trend, 95 % prediction interval",
            "disclaimer": DISCLAIMER}


OUTLOOK_WORDS = {"growing_fast": "projected to keep developing", "growing_slowly": "developing slowly",
                 "flat": "barely developing", "built_out": "already built out"}
