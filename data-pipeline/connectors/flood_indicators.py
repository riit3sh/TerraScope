"""Flood-relevant indicators from rasters. EVIDENCE ONLY - nothing here is a score.

* JRC Global Surface Water v1.4 - where open water was SEEN by Landsat, 1984-2021.
  It is not a flood-event history: short floods between revisits, floods under
  monsoon cloud and most urban street flooding are not captured.
* Copernicus DEM GLO-30 - a surface model (buildings and trees included). The parcel's
  elevation relative to the nearest mapped water feature is a TERRAIN INDICATOR, not
  HAND (no drainage connectivity is modelled) and not a flood probability.

Tiles are read from the shared local cache (``data-cache/rasters``) when a region has
been fetched, and otherwise read remotely, window by window, from the provider. A
read that fails is reported as unavailable, never as "no water".
"""

from __future__ import annotations

import math
import os
import threading
import time
from pathlib import Path
from typing import Any

import numpy as np
import rasterio
import requests
import shapely
from rasterio.features import geometry_mask
from rasterio.merge import merge
from shapely.geometry import mapping, shape

from connectors.elevation_dem import ElevationClient, ElevationError
from connectors.local_osm import LocalOSM
from connectors.regions import LocalDataMissing, data_root


# Bounded remote reads: a slow provider fails fast instead of stalling an analysis.
for _key, _value in {
    "GDAL_HTTP_TIMEOUT": "20",
    "GDAL_HTTP_CONNECTTIMEOUT": "10",
    "GDAL_HTTP_MAX_RETRY": "2",
    "GDAL_HTTP_RETRY_DELAY": "1",
    "GDAL_DISABLE_READDIR_ON_OPEN": "EMPTY_DIR",
    "CPL_VSIL_CURL_ALLOWED_EXTENSIONS": ".tif",
    "VSI_CACHE": "TRUE",
}.items():
    os.environ.setdefault(_key, _value)

BUFFER_M = 500.0
WATER_SEARCH_M = 2000.0
GSW_NODATA_MIN = 101  # occurrence is 0-100 %; 255 marks no observation
GSW_REMOTE = "https://storage.googleapis.com/global-surface-water/downloads2021"
DEM_REMOTE = "https://elevationeuwest.blob.core.windows.net/copernicus-dem/COP30_hh"
PC_SIGN = "https://planetarycomputer.microsoft.com/api/sas/v1/sign"
GSW_LICENCE = "Copernicus Programme, free of charge without restriction of use. Source: EC JRC/Google"
DEM_LICENCE = ("Copernicus DEM licence (free use). (c) DLR e.V. 2010-2014 and (c) Airbus Defence and Space GmbH "
               "2014-2018 provided under COPERNICUS by the European Union and ESA")
DEM_PRODUCT_DATE = "2021-04-22"
DEM_PERIOD = "TanDEM-X acquisitions 2011-2015"


def rasters_dir() -> Path:
    return data_root() / "rasters"


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


def _read_window(sources: list[str], bounds: tuple[float, float, float, float]):
    """Mosaic of the tiles (local paths or remote URLs) covering ``bounds``."""
    opened = []
    try:
        for source in sources:
            dataset = rasterio.open(source)
            b = dataset.bounds
            if b.right > bounds[0] and b.left < bounds[2] and b.top > bounds[1] and b.bottom < bounds[3]:
                opened.append(dataset)
            else:
                dataset.close()
        if not opened:
            return None, None
        array, transform = merge(opened, bounds=bounds)
        return array[0], transform
    finally:
        for dataset in opened:
            dataset.close()


def _masked(array, transform, geometry) -> np.ndarray:
    mask = geometry_mask([mapping(geometry)], out_shape=array.shape, transform=transform, invert=True, all_touched=True)
    return array[mask]


def _tiles(bounds, step: int):
    """(west, south) corners of the ``step``-degree grid cells overlapping ``bounds``."""
    west, south, east, north = bounds
    for x in range(math.floor(west / step) * step, math.floor(east / step) * step + 1, step):
        for y in range(math.floor(south / step) * step, math.floor(north / step) * step + 1, step):
            yield x, y


def _hemi(value: int, positive: str, negative: str, width: int) -> str:
    return f"{positive if value >= 0 else negative}{abs(value):0{width}d}" if width else f"{abs(value)}{positive if value >= 0 else negative}"


# --- JRC Global Surface Water ---------------------------------------------------

def gsw_sources(layer: str, bounds) -> tuple[list[str], str]:
    """Tile paths for ``layer``; local where cached, remote otherwise."""
    sources, local = [], 0
    for west, south in _tiles(bounds, 10):
        # JRC tiles are named by their north-west corner: 70E_20N covers 70-80E, 10-20N.
        name = f"{layer}_{_hemi(west, 'E', 'W', 0)}_{_hemi(south + 10, 'N', 'S', 0)}v1_4_2021.tif"
        path = rasters_dir() / "gsw" / name
        if path.exists():
            sources.append(str(path)); local += 1
        else:
            sources.append(f"/vsicurl/{GSW_REMOTE}/{layer}/{name}")
    return sources, "local tiles" if local == len(sources) else "read remotely from JRC" if not local else "local and remote tiles"


def surface_water(geojson_polygon: dict[str, Any]) -> dict[str, Any]:
    parcel = shape(geojson_polygon)
    ring = buffered(parcel, BUFFER_M)
    bounds = ring.bounds
    occurrence_sources, access = gsw_sources("occurrence", bounds)
    extent_sources, _ = gsw_sources("extent", bounds)
    occurrence, transform = _read_window(occurrence_sources, bounds)
    extent, extent_transform = _read_window(extent_sources, bounds)
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

    return {
        "parcel": stats(parcel),
        "within_buffer": stats(ring),
        "buffer_m": BUFFER_M,
        "observation_period": "1984-03 to 2021-12",
        "resolution_m": 30,
        "dataset": "JRC Global Surface Water v1.4",
        "data_access": access,
    }


# --- Copernicus DEM ------------------------------------------------------------

def _dem_name(lat: float, lon: float) -> str:
    lat_i, lon_i = math.floor(lat), math.floor(lon)
    return f"Copernicus_DSM_COG_10_{_hemi(lat_i, 'N', 'S', 2)}_00_{_hemi(lon_i, 'E', 'W', 3)}_00_DEM.tif"


_signed: dict[str, tuple[str, float]] = {}
_signed_lock = threading.Lock()


def _sign(href: str) -> str:
    """Planetary Computer SAS-signed URL, reused for 30 minutes."""
    with _signed_lock:
        cached = _signed.get(href)
        if cached and cached[1] > time.time():
            return cached[0]
    response = requests.get(PC_SIGN, params={"href": href}, timeout=15)
    response.raise_for_status()
    url = response.json()["href"]
    with _signed_lock:
        _signed[href] = (url, time.time() + 1800)
    return url


def dem_source(lat: float, lon: float) -> str:
    name = _dem_name(lat, lon)
    path = rasters_dir() / "dem" / name
    return str(path) if path.exists() else _sign(f"{DEM_REMOTE}/{name}")


def dem_access(lat: float, lon: float) -> str:
    return "local tiles" if (rasters_dir() / "dem" / _dem_name(lat, lon)).exists() else "read remotely from Planetary Computer"


def sample_dem(points: list[tuple[float, float]]) -> list[float | None]:
    """Elevation at ``(lat, lon)`` points; None where no tile covers the point (e.g. open sea)."""
    by_tile: dict[str, list[int]] = {}
    for index, (lat, lon) in enumerate(points):
        by_tile.setdefault(_dem_name(lat, lon), []).append(index)
    values: list[float | None] = [None] * len(points)
    for indices in by_tile.values():
        lat, lon = points[indices[0]]
        try:
            source = dem_source(lat, lon)
            with rasterio.open(source) as dataset:
                for index, sample in zip(indices, dataset.sample([(points[i][1], points[i][0]) for i in indices])):
                    value = float(sample[0])
                    values[index] = value if math.isfinite(value) and value > -1000 else None
        except (rasterio.errors.RasterioIOError, requests.RequestException):
            continue  # no tile (sea) or provider error: those samples stay None
    return values


class LocalDemElevationClient(ElevationClient):
    """The terrain-position indicator, sampled from Copernicus GLO-30 (local or remote tiles)."""

    source_reference = "Copernicus DEM GLO-30 (via Microsoft Planetary Computer)"

    def get_elevations(self, points: list[tuple[float, float]]) -> list[float | None]:
        return sample_dem(points)

    def get_elevation(self, lat: float, lon: float) -> float:
        value = sample_dem([(lat, lon)])[0]
        if value is None:
            raise ElevationError("No Copernicus DEM value is available at this point.")
        return value


def _dem_window(bounds):
    sources = [dem_source(south + 0.5, west + 0.5) for west, south in _tiles(bounds, 1)]
    return _read_window(sources, bounds)


def terrain_above_water(geojson_polygon: dict[str, Any], osm: LocalOSM | None) -> dict[str, Any]:
    """Parcel elevation, and - when a regional OSM store is installed - its height
    relative to the nearest mapped water feature."""
    parcel = shape(geojson_polygon)
    centre = parcel.centroid
    waterway = osm.nearest(centre.x, centre.y, "waterway", max_distance_m=WATER_SEARCH_M) if osm else None
    water_body = osm.nearest(centre.x, centre.y, "water", max_distance_m=WATER_SEARCH_M) if osm else None
    candidates = [(hit, kind) for hit, kind in ((waterway, "waterway"), (water_body, "water body")) if hit]
    nearest, kind = min(candidates, key=lambda pair: pair[0]["distance_m"]) if candidates else (None, None)

    region = parcel if nearest is None else parcel.union(shapely.Point(nearest["lon"], nearest["lat"]).buffer(0.001))
    dem, transform = _dem_window(region.bounds)
    if dem is None:
        raise LocalDataMissing("No Copernicus DEM tile covers this parcel.")
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
        "search_radius_m": WATER_SEARCH_M if osm else None,
        "water_features_available": osm is not None,
        "dataset": "Copernicus DEM GLO-30" + (" + OpenStreetMap water features" if osm else ""),
        "resolution_m": 30,
        "data_access": dem_access(centre.y, centre.x),
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
