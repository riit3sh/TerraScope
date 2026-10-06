"""Coverage (all of India) and selection of installed regional data caches.

Coverage is India-wide: a parcel is accepted when it lies inside India and is
rejected, before any collector runs, when it does not. Regional caches (a local
OpenStreetMap store per region, built by ``terrascope.cmd fetch-data <region>``)
only add evidence; a parcel in a region without one is still analysed with every
collector that works India-wide, and the missing layer says how to install it.

Boundary: geoBoundaries gbOpen IND ADM1 (DataMeet India / Election Commission of
India, CC BY 2.5 IN), 36 states and union territories. It is not a Survey of
India boundary; coastlines and borders are generalised, so a parcel may extend
up to OUTSIDE_TOLERANCE outside it before it is refused.
"""

from __future__ import annotations

import json
import os
import re
import threading
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import shapely
from shapely.geometry import shape
from shapely.strtree import STRtree


INDIA_DIR = "india"
STATES_FILE = "india_states.geojson"
UNION_FILE = "india_boundary.wkb"
MANIFEST_NAME = "manifest.json"
REGION_STORE = "osm.sqlite"
REGION_BOUNDARY = "boundary.geojson"
# Share of a parcel's area allowed outside the generalised boundary (coast, borders).
OUTSIDE_TOLERANCE = 0.01


class LocalDataMissing(RuntimeError):
    """A local dataset needed for this step has not been installed."""


def slug(name: str) -> str:
    """'Tamil Nādu' -> 'tamil-nadu': the region name used by fetch-data."""
    ascii_name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", ascii_name.lower()).strip("-")


def data_root() -> Path:
    configured = os.getenv("TERRASCOPE_DATA_DIR")
    if configured:
        return Path(configured)
    return Path(__file__).resolve().parents[2] / "data-cache"


def read_manifest(directory: Path) -> dict[str, Any]:
    try:
        return json.loads((directory / MANIFEST_NAME).read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


# --- India coverage ---------------------------------------------------------------

class IndiaCoverage:
    def __init__(self, states: list[dict[str, Any]], india, properties: dict[str, Any]) -> None:
        self.states = states
        self.india = india
        shapely.prepare(self.india)
        self.tree = STRtree([state["geometry"] for state in states])
        self.properties = properties

    @classmethod
    def load(cls, root: Path | None = None) -> "IndiaCoverage":
        directory = (root or data_root()) / INDIA_DIR
        states_path, union_path = directory / STATES_FILE, directory / UNION_FILE
        if not states_path.exists() or not union_path.exists():
            raise LocalDataMissing(
                f"The India coverage boundary is not installed ({directory}). Run: terrascope.cmd fetch-data"
            )
        collection = json.loads(states_path.read_text(encoding="utf-8"))
        states = [
            {
                "name": feature["properties"].get("shapeName"),
                "iso": feature["properties"].get("shapeISO"),
                "geometry": shape(feature["geometry"]),
            }
            for feature in collection["features"]
        ]
        india = shapely.from_wkb(union_path.read_bytes())
        return cls(states, india, read_manifest(directory))

    def check(self, geojson_polygon: dict[str, Any]) -> dict[str, Any]:
        """Is the whole parcel in India, and which states/UTs does it fall in?"""
        parcel = shape(geojson_polygon)
        if not parcel.is_valid:
            parcel = shapely.make_valid(parcel)
        area = parcel.area or 1e-18
        inside_share = parcel.intersection(self.india).area / area if self.india.intersects(parcel) else 0.0
        # Every state the parcel touches, with its share, so a parcel on a state border
        # is never silently assigned to the state of its centroid.
        states = []
        for index in self.tree.query(parcel, predicate="intersects"):
            state = self.states[int(index)]
            share = parcel.intersection(state["geometry"]).area / area
            if share > 0:
                states.append({"name": state["name"], "iso": state["iso"], "share": round(share, 4)})
        states.sort(key=lambda item: item["share"], reverse=True)
        if inside_share >= 1.0 - OUTSIDE_TOLERANCE:
            status, reason = "inside", None
        elif inside_share > 0:
            status = "outside_india"
            reason = (
                f"Only {inside_share * 100:.1f}% of the parcel lies inside India. Draw the parcel entirely "
                "inside India; TerraScope does not assess land across the national boundary."
            )
        else:
            status, reason = "outside_india", "The parcel lies outside India. TerraScope covers India only."
        return {
            "status": status,
            "reason": reason,
            "inside_india_share": round(min(1.0, inside_share), 4),
            "states": states,
            "crosses_state_border": len(states) > 1,
            "boundary_source": self.properties.get("source"),
            "boundary_licence": self.properties.get("licence"),
            "boundary_as_of": self.properties.get("data_as_of"),
        }


_lock = threading.Lock()
_coverage: dict[str, IndiaCoverage] = {}


def india_coverage() -> IndiaCoverage:
    """Loaded once per process (36 detailed state polygons)."""
    key = str(data_root())
    with _lock:
        if key not in _coverage:
            _coverage[key] = IndiaCoverage.load()
        return _coverage[key]


# --- regional caches --------------------------------------------------------------

@dataclass
class Region:
    slug: str
    path: Path
    label: str
    coverage: Any  # shapely geometry the regional OSM store is complete for
    meta: dict[str, Any] = field(default_factory=dict)

    @property
    def osm_store(self) -> Path:
        return self.path / REGION_STORE


_regions: dict[str, list[Region]] = {}


def installed_regions(root: Path | None = None) -> list[Region]:
    """Regions with a built store, read once per process (fetch-data asks for a restart)."""
    key = str(root or data_root())
    with _lock:
        if key not in _regions:
            _regions[key] = _scan_regions(Path(key))
        return _regions[key]


def _scan_regions(root: Path) -> list[Region]:
    regions = []
    for directory in sorted((root / "regions").glob("*")):
        boundary, store = directory / REGION_BOUNDARY, directory / REGION_STORE
        if not boundary.exists() or not store.exists():
            continue
        feature = json.loads(boundary.read_text(encoding="utf-8"))
        geometry = shape(feature["geometry"])
        shapely.prepare(geometry)
        meta = read_manifest(directory)
        regions.append(Region(directory.name, directory, meta.get("label") or directory.name, geometry, meta))
    return regions


def region_for(geojson_polygon: dict[str, Any], root: Path | None = None) -> Region | None:
    """The installed region whose OSM store fully covers this parcel, if any.

    The store is clipped to the region plus a margin, so a parcel inside the region's
    coverage polygon has complete data within the nearest-feature search radius.
    """
    parcel = shape(geojson_polygon)
    for region in installed_regions(root):
        if region.coverage.covers(parcel):
            return region
    return None
