"""Distance from a parcel to the sea, to decide whether coastal flooding is relevant at all.

The OpenStreetMap coastline (regions/india/coastline.sqlite) is measured from the drawn boundary. Within
COASTAL_BAND_M of it a plot is "coastal" and coastal flooding is reported (still NOT ASSESSED: no storm-surge data);
beyond it the mechanism is "not applicable". The band is a rule of thumb, not a hazard boundary: tidal rivers and
backwaters can carry sea water further inland. Without the store, the distance is unknown and nothing is assumed.
"""

from __future__ import annotations

import math
import sqlite3
from pathlib import Path
from typing import Any

import shapely
from shapely.geometry import shape

STORE_NAME = "coastline.sqlite"
COASTAL_BAND_M = 10_000.0
SEARCH_M = 50_000.0


def coast_distance(geojson_polygon: dict[str, Any], store: Path | None) -> dict[str, Any]:
    if store is None or not Path(store).exists():
        return {"status": "unavailable", "reason": "the coastline map is not built (fetch_data.py --coastline)"}
    parcel = shape(geojson_polygon)
    lon0, lat0 = parcel.centroid.x, parcel.centroid.y
    sx, sy = 111_320.0 * math.cos(math.radians(lat0)), 110_574.0
    dlon, dlat = SEARCH_M / sx, SEARCH_M / sy
    west, south, east, north = parcel.bounds
    connection = sqlite3.connect(f"file:{Path(store).as_posix()}?mode=ro", uri=True)
    try:
        rows = connection.execute(
            "SELECT f.geom FROM features_rtree r JOIN features f ON f.id = r.id "
            "WHERE r.minx <= ? AND r.maxx >= ? AND r.miny <= ? AND r.maxy >= ?",
            (east + dlon, west - dlon, north + dlat, south - dlat)).fetchall()
        meta = dict(connection.execute("SELECT key, value FROM store_meta").fetchall())
    finally:
        connection.close()

    def project(coords):
        out = coords.copy()
        out[:, 0] = (coords[:, 0] - lon0) * sx
        out[:, 1] = (coords[:, 1] - lat0) * sy
        return out

    base = {"status": "assessed", "band_m": COASTAL_BAND_M, "source": meta.get("source"),
            "data_as_of": (meta.get("data_as_of") or "")[:10] or None}
    if not rows:
        return {**base, "distance_m": None, "beyond_m": SEARCH_M, "coastal": False}
    lines = shapely.transform(shapely.from_wkb([r[0] for r in rows]), project)
    distance = float(shapely.distance(lines, shapely.transform(parcel, project)).min())
    if distance > SEARCH_M:
        return {**base, "distance_m": None, "beyond_m": SEARCH_M, "coastal": False}
    return {**base, "distance_m": round(distance, 1), "coastal": distance <= COASTAL_BAND_M}
