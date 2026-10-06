"""Regional OpenStreetMap store: format and nearest-feature queries.

One store per installed region, built by ``terrascope.cmd fetch-data <region>``
(see ``fetch_data.py``) from a Geofabrik India zone extract. Analyses read it from
disk, so accessibility and water distances do not depend on a public Overpass
server answering in time. Region selection lives in ``regions.py``.

Distances are straight lines from the parcel centroid to the nearest point on the
feature's full geometry (every vertex of a road, the whole outline of a lake),
never to a midpoint or centre. They are proximity, not routed travel distance.
"""

from __future__ import annotations

import json
import math
import sqlite3
from pathlib import Path
from typing import Any, Iterable

import shapely
from shapely.geometry import Point

from connectors.regions import LocalDataMissing


SCHEMA = """
CREATE TABLE IF NOT EXISTS features (
    id INTEGER PRIMARY KEY,
    layer TEXT NOT NULL,
    class TEXT,
    name TEXT,
    osm_id TEXT,
    tags TEXT,
    geom BLOB NOT NULL
);
CREATE VIRTUAL TABLE IF NOT EXISTS features_rtree USING rtree(id, minx, maxx, miny, maxy);
CREATE TABLE IF NOT EXISTS store_meta (key TEXT PRIMARY KEY, value TEXT);
"""

# Search radii widen until something is found, so a dense city never loads
# every road within 5 km and a rural parcel still finds its nearest feature.
SEARCH_STEPS_M = (250.0, 1000.0, 3000.0, 5000.0)


# --- store writing (used by tn_data.py and the tests) ------------------------

def create_store(path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(path)
    connection.executescript(SCHEMA)
    return connection


def write_features(connection: sqlite3.Connection, rows: Iterable[tuple]) -> int:
    """Insert ``(layer, class, name, osm_id, tags_dict, shapely_geometry)`` rows."""
    batch = list(rows)
    if not batch:
        return 0
    geometries = [row[5] for row in batch]
    bounds = shapely.bounds(geometries)
    cursor = connection.execute("SELECT COALESCE(MAX(id), 0) FROM features")
    next_id = cursor.fetchone()[0] + 1
    feature_rows, index_rows = [], []
    for offset, (row, box) in enumerate(zip(batch, bounds)):
        layer, cls, name, osm_id, tags, geometry = row
        identifier = next_id + offset
        feature_rows.append((identifier, layer, cls, name, osm_id, json.dumps(tags or {}), shapely.to_wkb(geometry)))
        index_rows.append((identifier, box[0], box[2], box[1], box[3]))
    connection.executemany("INSERT INTO features VALUES (?, ?, ?, ?, ?, ?, ?)", feature_rows)
    connection.executemany("INSERT INTO features_rtree VALUES (?, ?, ?, ?, ?)", index_rows)
    return len(batch)


# --- nearest-feature queries -----------------------------------------------------

class LocalOSM:
    """Read-only nearest-feature lookups against the local store."""

    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        if not self.path.exists():
            raise LocalDataMissing(
                f"The local OpenStreetMap store is not installed ({self.path}). Run: terrascope.cmd fetch-data"
            )
        # Read-only URI: analyses can never modify the built data.
        self.connection = sqlite3.connect(f"file:{self.path.as_posix()}?mode=ro", uri=True, check_same_thread=False)
        self.meta = dict(self.connection.execute("SELECT key, value FROM store_meta").fetchall())

    def close(self) -> None:
        self.connection.close()

    @staticmethod
    def _projector(lon0: float, lat0: float):
        """Local equirectangular metres about the origin (error far below 0.1% over 5 km)."""
        scale_lon = 111_320.0 * math.cos(math.radians(lat0))
        scale_lat = 110_574.0

        def forward(coords):
            out = coords.copy()
            out[:, 0] = (coords[:, 0] - lon0) * scale_lon
            out[:, 1] = (coords[:, 1] - lat0) * scale_lat
            return out

        def backward(x: float, y: float) -> tuple[float, float]:
            return lon0 + x / scale_lon, lat0 + y / scale_lat

        return forward, backward, scale_lon, scale_lat

    def nearest(
        self,
        lon: float,
        lat: float,
        layer: str,
        classes: Iterable[str] | None = None,
        max_distance_m: float = 5000.0,
    ) -> dict[str, Any] | None:
        """Nearest feature of ``layer`` (optionally restricted to ``classes``)."""
        forward, backward, scale_lon, scale_lat = self._projector(lon, lat)
        wanted = set(classes) if classes is not None else None
        origin = Point(0.0, 0.0)
        for radius in [step for step in SEARCH_STEPS_M if step < max_distance_m] + [max_distance_m]:
            dlon, dlat = radius / scale_lon, radius / scale_lat
            rows = self.connection.execute(
                "SELECT f.class, f.name, f.osm_id, f.tags, f.geom FROM features_rtree r "
                "JOIN features f ON f.id = r.id "
                "WHERE r.minx <= ? AND r.maxx >= ? AND r.miny <= ? AND r.maxy >= ? AND f.layer = ?",
                (lon + dlon, lon - dlon, lat + dlat, lat - dlat, layer),
            ).fetchall()
            if wanted is not None:
                rows = [row for row in rows if row[0] in wanted]
            if not rows:
                continue
            geometries = shapely.transform(shapely.from_wkb([row[4] for row in rows]), forward)
            distances = shapely.distance(geometries, origin)
            best = int(distances.argmin())
            distance = float(distances[best])
            # Only a hit inside the searched box is guaranteed to be the nearest.
            if distance > radius:
                continue
            on_feature = shapely.shortest_line(geometries[best], origin).coords[0]
            point_lon, point_lat = backward(*on_feature)
            cls, name, osm_id, tags, _ = rows[best]
            return {
                "distance_m": round(distance, 2),
                "class": cls,
                "name": name,
                "osm_id": osm_id,
                "tags": json.loads(tags or "{}"),
                "lon": round(point_lon, 6),
                "lat": round(point_lat, 6),
            }
        return None
