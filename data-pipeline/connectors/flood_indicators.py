"""Flood-relevant indicators from local rasters. EVIDENCE ONLY - nothing here is a score.

* JRC Global Surface Water v1.4 - where open water was SEEN by Landsat, 1984-2021.
  It is not a flood-inundation history: short floods between revisits, floods under
  monsoon cloud and most urban street flooding are not captured.
* Copernicus DEM GLO-30 - a surface model (buildings and trees included). The parcel's
  height above the nearest mapped water feature is a TERRAIN INDICATOR, not HAND
  (no drainage network or flow routing) and not a flood probability.
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any

import numpy as np
import rasterio
import shapely
from rasterio.features import geometry_mask
from rasterio.merge import merge
from shapely.geometry import mapping, shape

from connectors.elevation_dem import ElevationClient, ElevationError
from connectors.local_osm import LocalDataMissing, LocalOSM, data_dir, load_manifest


BUFFER_M = 500.0
WATER_SEARCH_M = 2000.0
GSW_NODATA_MIN = 101  # occurrence is 0-100 %; 255 marks no observation


def _transformers(lon0: float, lat0: float):
    scale_lon = 111_320.0 * math.cos(math.radians(lat0))
    scale_lat = 110_574.0

    def to_m(coords):
        out = coords.copy()
        out[:, 0] = (coords[:, 0] - lon0) * scale_lon
        out[:, 1] = (coords[:, 1] - lat0) * scale_lat
        return out

    def to_deg(coords):
        out = coords.copy()
        out[:, 0] = lon0 + coords[:, 0] / scale_lon
        out[:, 1] = lat0 + coords[:, 1] / scale_lat
        return out

    return to_m, to_deg


def buffered(parcel, metres: float):
    """Parcel grown by ``metres``, built in local metres and returned in lon/lat."""
    centre = parcel.centroid
    to_m, to_deg = _transformers(centre.x, centre.y)
    return shapely.transform(shapely.transform(parcel, to_m).buffer(metres), to_deg)


def _read_window(paths: list[Path], bounds: tuple[float, float, float, float]):
    """Mosaic of the tiles covering ``bounds`` (all tiles are EPSG:4326)."""
    sources = []
    try:
        for path in paths:
            source = rasterio.open(path)
            b = source.bounds
            if b.right > bounds[0] and b.left < bounds[2] and b.top > bounds[1] and b.bottom < bounds[3]:
                sources.append(source)
            else:
                source.close()
        if not sources:
            return None, None
        array, transform = merge(sources, bounds=bounds)
        return array[0], transform
    finally:
        for source in sources:
            source.close()


def _masked(array, transform, geometry) -> np.ndarray:
    mask = geometry_mask([mapping(geometry)], out_shape=array.shape, transform=transform, invert=True, all_touched=True)
    return array[mask]


# --- JRC Global Surface Water ---------------------------------------------------

def surface_water(geojson_polygon: dict[str, Any], directory: Path | None = None) -> dict[str, Any]:
    folder = (directory or data_dir()) / "gsw"
    occurrence_tiles = sorted(folder.glob("occurrence_*.tif"))
    extent_tiles = sorted(folder.glob("extent_*.tif"))
    if not occurrence_tiles or not extent_tiles:
        raise LocalDataMissing("JRC Global Surface Water tiles are not installed. Run: terrascope.cmd fetch-data")
    parcel = shape(geojson_polygon)
    ring = buffered(parcel, BUFFER_M)
    bounds = ring.bounds
    occurrence, transform = _read_window(occurrence_tiles, bounds)
    extent, extent_transform = _read_window(extent_tiles, bounds)
    if occurrence is None or extent is None:
        raise LocalDataMissing("No JRC Global Surface Water tile covers this parcel.")

    def stats(geometry) -> dict[str, Any]:
        occ = _masked(occurrence, transform, geometry)
        occ = occ[occ < GSW_NODATA_MIN].astype("float64")
        ext = _masked(extent, extent_transform, geometry)
        ext = ext[ext <= 1]
        return {
            "pixels": int(occ.size),
            "occurrence_max_pct": int(occ.max()) if occ.size else None,
            "occurrence_mean_pct": round(float(occ.mean()), 2) if occ.size else None,
            # Share of pixels where water was detected at least once (the "maximum extent").
            "water_ever_fraction": round(float((ext == 1).mean()), 4) if ext.size else None,
        }

    inside = stats(parcel)
    around = stats(ring)
    return {
        "parcel": inside,
        "within_buffer": around,
        "buffer_m": BUFFER_M,
        "observation_period": "1984-03 to 2021-12",
        "resolution_m": 30,
        "dataset": "JRC Global Surface Water v1.4",
    }


# --- Copernicus DEM ------------------------------------------------------------

def _dem_tile(directory: Path, lat: float, lon: float) -> Path:
    lat_i, lon_i = math.floor(lat), math.floor(lon)
    ns, ew = ("N" if lat_i >= 0 else "S"), ("E" if lon_i >= 0 else "W")
    return directory / "dem" / f"Copernicus_DSM_COG_10_{ns}{abs(lat_i):02d}_00_{ew}{abs(lon_i):03d}_00_DEM.tif"


def dem_installed(directory: Path | None = None) -> bool:
    return any(((directory or data_dir()) / "dem").glob("*.tif"))


def sample_dem(points: list[tuple[float, float]], directory: Path | None = None) -> list[float | None]:
    """Elevation at ``(lat, lon)`` points; None where no tile covers the point."""
    folder = directory or data_dir()
    values: list[float | None] = []
    for lat, lon in points:
        path = _dem_tile(folder, lat, lon)
        if not path.exists():
            values.append(None)
            continue
        with rasterio.open(path) as source:
            value = float(next(source.sample([(lon, lat)]))[0])
        values.append(value if math.isfinite(value) and value > -1000 else None)
    return values


class LocalDemElevationClient(ElevationClient):
    """The existing terrain-position indicator, sampled from local GLO-30 tiles."""

    source_reference = "Copernicus DEM GLO-30 (local tiles, via Microsoft Planetary Computer)"

    def get_elevations(self, points: list[tuple[float, float]]) -> list[float | None]:
        return sample_dem(points)

    def get_elevation(self, lat: float, lon: float) -> float:
        value = sample_dem([(lat, lon)])[0]
        if value is None:
            raise ElevationError("No local Copernicus DEM tile covers this point.")
        return value


def _dem_window(bounds, directory: Path):
    corners = {(_dem_tile(directory, lat, lon)) for lat in (bounds[1], bounds[3]) for lon in (bounds[0], bounds[2])}
    return _read_window(sorted(path for path in corners if path.exists()), bounds)


def terrain_above_water(
    geojson_polygon: dict[str, Any], osm: LocalOSM, directory: Path | None = None
) -> dict[str, Any]:
    """Parcel elevation and its height above the nearest mapped water feature."""
    folder = directory or data_dir()
    parcel = shape(geojson_polygon)
    centre = parcel.centroid
    waterway = osm.nearest(centre.x, centre.y, "waterway", max_distance_m=WATER_SEARCH_M)
    water_body = osm.nearest(centre.x, centre.y, "water", max_distance_m=WATER_SEARCH_M)
    candidates = [(hit, kind) for hit, kind in ((waterway, "waterway"), (water_body, "water body")) if hit]
    nearest, kind = min(candidates, key=lambda pair: pair[0]["distance_m"]) if candidates else (None, None)

    region = parcel if nearest is None else parcel.union(shapely.Point(nearest["lon"], nearest["lat"]).buffer(0.001))
    dem, transform = _dem_window(region.bounds, folder)
    if dem is None:
        raise LocalDataMissing("No local Copernicus DEM tile covers this parcel.")
    inside = _masked(dem, transform, parcel).astype("float64")
    inside = inside[np.isfinite(inside) & (inside > -1000)]
    if not inside.size:
        raise ElevationError("The DEM has no valid pixels inside the parcel.")
    parcel_elevation = float(np.median(inside))

    result: dict[str, Any] = {
        "parcel_elevation_m": round(parcel_elevation, 1),
        "parcel_elevation_basis": f"median of {inside.size} DEM pixels touching the parcel",
        "parcel_elevation_range_m": [round(float(inside.min()), 1), round(float(inside.max()), 1)],
        "nearest_water_feature_kind": kind,
        "nearest_water_feature_class": nearest["class"] if nearest else None,
        "nearest_water_feature_name": nearest["name"] if nearest else None,
        "nearest_water_feature_distance_m": nearest["distance_m"] if nearest else None,
        "water_feature_elevation_m": None,
        "elevation_above_nearest_water_m": None,
        "search_radius_m": WATER_SEARCH_M,
        "dataset": "Copernicus DEM GLO-30 + OpenStreetMap water features",
        "resolution_m": 30,
    }
    if nearest:
        # A surface model reads bank vegetation or a bridge over a narrow drain, so take
        # the lowest pixel within ~45 m of the mapped water point as the water level.
        row, col = rasterio.transform.rowcol(transform, nearest["lon"], nearest["lat"])
        window = dem[max(0, row - 1): row + 2, max(0, col - 1): col + 2].astype("float64")
        window = window[np.isfinite(window) & (window > -1000)]
        if window.size:
            water_level = float(window.min())
            result["water_feature_elevation_m"] = round(water_level, 1)
            result["elevation_above_nearest_water_m"] = round(parcel_elevation - water_level, 1)
    return result


def dataset_notes() -> dict[str, Any]:
    """Licence, version and date of each raster, as recorded by fetch-data."""
    manifest = load_manifest()
    return {"jrc_gsw": manifest.get("jrc_gsw") or {}, "copernicus_dem": manifest.get("copernicus_dem") or {}}

