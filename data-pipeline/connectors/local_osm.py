"""Local Tamil Nadu OpenStreetMap store: coverage check and nearest-feature queries.

Built once by ``terrascope.cmd fetch-data`` (see ``tn_data.py``) from the Geofabrik
southern-zone extract. Analyses read it from disk, so accessibility and water
distances no longer depend on a public Overpass server answering in time.

Distances are straight lines from the parcel centroid to the nearest point on the
feature's full geometry (every vertex of a road, the whole outline of a lake),
never to a midpoint or centre. They are proximity, not routed travel distance.
"""

from __future__ import annotations

import json
import math
import os
import sqlite3
import threading
from pathlib import Path
from typing import Any, Iterable

import shapely
from shapely.geometry import Point, shape


STORE_NAME = "tn_osm.sqlite"
BOUNDARY_NAME = "tn_boundary.geojson"
MANIFEST_NAME = "manifest.json"

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


class LocalDataMissing(RuntimeError):
    """The local Tamil Nadu data has not been built yet."""


def data_dir() -> Path:
    configured = os.getenv("TERRASCOPE_TN_DATA_DIR")
    if configured:
        return Path(configured)
    return Path(__file__).resolve().parents[2] / "tn-data"


def load_manifest(directory: Path | None = None) -> dict[str, Any]:
    path = (directory or data_dir()) / MANIFEST_NAME
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


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


# --- coverage --------------------------------------------------------------------

class Coverage:
    """Tamil Nadu boundary, with the Puducherry and Karaikal enclaves removed."""

    def __init__(self, geometry, properties: dict[str, Any]) -> None:
        self.geometry = geometry
        shapely.prepare(self.geometry)
        self.properties = properties

    @classmethod
    def load(cls, directory: Path | None = None) -> "Coverage":
        path = (directory or data_dir()) / BOUNDARY_NAME
        if not path.exists():
            raise LocalDataMissing(
                f"The Tamil Nadu coverage boundary is not installed ({path}). Run: terrascope.cmd fetch-data"
            )
        feature = json.loads(path.read_text(encoding="utf-8"))
        return cls(shape(feature["geometry"]), feature.get("properties") or {})

    def check(self, geojson_polygon: dict[str, Any]) -> dict[str, Any]:
        """Whether the whole drawn polygon lies inside coverage."""
        parcel = shape(geojson_polygon)
        if not parcel.is_valid:
            parcel = shapely.make_valid(parcel)
        inside = bool(self.geometry.covers(parcel))
        overlaps = inside or bool(self.geometry.intersects(parcel))
        if inside:
            status, reason = "inside", None
        elif overlaps:
            status = "outside"
            reason = (
                "The boundary crosses the edge of Tamil Nadu coverage (the state border, the coast, "
                "or a Puducherry/Karaikal enclave, which keeps separate land records). Draw the parcel "
                "entirely inside Tamil Nadu."
            )
        else:
            status = "outside"
            reason = "The parcel lies outside Tamil Nadu. TerraScope currently covers Tamil Nadu only."
        return {
            "status": status,
            "reason": reason,
            "boundary_source": self.properties.get("source"),
            "boundary_licence": self.properties.get("licence"),
            "boundary_as_of": self.properties.get("data_as_of"),
        }


_coverage_lock = threading.Lock()
_coverage_cache: dict[str, Coverage] = {}


def coverage() -> Coverage:
    """Load the boundary once per process; it is several MB of vertices."""
    key = str(data_dir())
    with _coverage_lock:
        if key not in _coverage_cache:
            _coverage_cache[key] = Coverage.load()
        return _coverage_cache[key]


# --- nearest-feature queries -----------------------------------------------------

class LocalOSM:
    """Read-only nearest-feature lookups against the local store."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = path or (data_dir() / STORE_NAME)
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
