"""Modelled river-flood exposure from the JRC global river flood hazard maps.

Source: Global river flood hazard maps v2.1.2 (Copernicus Emergency Management
Service / GloFAS; LISFLOOD hydrology + LISFLOOD-FP inundation), CC BY 4.0,
doi:10.2905/JRC.VD32YWG. Water depth in metres at 3 arc-seconds (~90 m) for the
1-in-10 to 1-in-500-year return periods.

What it is: MODELLED river (fluvial) inundation for statistical scenarios on rivers
whose basins exceed ~500 km2. What it is not: an observed flood history, a building-
level assessment, or an assessment of rainfall waterlogging (pluvial), coastal surge,
dam-break or small-stream flooding. JRC states it is not an official hazard map.

Cell semantics, checked against the tiles (2026-10-06): depth > 0 is modelled
inundation; the nodata value (-9999) is "no modelled inundation in this scenario"
on land - and also open sea, which the files do not distinguish - so it is never
reported as "zero risk". Permanent-water cells carry depths and are excluded from
flood exposure. Spurious-depth cells (>10 m in small channels, plus 2 km) have
unreliable depths and are flagged. A tile that cannot be read leaves that part of the
parcel unassessed; it is never counted as dry.
"""

from __future__ import annotations

import hashlib
import json
import math
import tempfile
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import numpy as np
import rasterio
import requests
import shapely
from rasterio.windows import Window, from_bounds
from shapely.geometry import shape

from connectors import flood_indicators  # also sets bounded GDAL HTTP options
from connectors.regions import data_root


DATASET = "JRC global river flood hazard maps v2.1.2"
VERSION = "2.1.2"
BASE_URL = "https://jeodpp.jrc.ec.europa.eu/ftp/jrc-opendata/CEMS-GLOFAS/flood_hazard"
RETURN_PERIODS = (10, 20, 50, 75, 100, 200, 500)
# Surroundings: a parcel just outside the modelled floodplain is reported as such.
SURROUNDINGS_M = 500.0
RESULT_FORMAT = 2  # bump when the result fields change, so cached results are recomputed
NODATA_DEPTH = -9999.0
LICENCE = "CC BY 4.0 - (c) European Union, Copernicus Emergency Management Service (JRC)"
CITATION = "Baugh et al., Global river flood hazard maps, European Commission JRC, doi:10.2905/JRC.VD32YWG"


class RiverFloodUnavailable(RuntimeError):
    """The hazard maps could not be read for this parcel."""


def cache_dir() -> Path:
    return data_root() / "flood-hazard"


# --- tile index -------------------------------------------------------------------

_index_lock = threading.Lock()
_index: list[tuple[str, Any]] | None = None


def tile_index() -> list[tuple[str, Any]]:
    """(file prefix e.g. 'ID193_N20_E80', extent) for every tile; downloaded once and cached."""
    global _index
    with _index_lock:
        if _index is not None:
            return _index
        path = cache_dir() / "tile_extents.geojson"
        if not path.exists():
            try:
                response = requests.get(f"{BASE_URL}/tile_extents.geojson", timeout=30)
                response.raise_for_status()
            except requests.RequestException as error:
                raise RiverFloodUnavailable(f"JRC tile index could not be downloaded: {error}") from error
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(response.content)
        features = json.loads(path.read_text(encoding="utf-8"))["features"]
        _index = [(f"ID{f['properties']['id']}_{f['properties']['name']}", shape(f["geometry"])) for f in features]
        return _index


def _layer_path(prefix: str, layer: str) -> str:
    """Local copy under data-cache/flood-hazard/tiles if present, else the provider URL."""
    if layer.startswith("RP"):
        relative = f"{layer}/{prefix}_{layer}_depth.tif"
    elif layer == "permanent_water":
        relative = f"Permanent_WaterBodies/{prefix}_permanent_water.tif"
    else:
        relative = f"Spurious_Depths/{prefix}_spurious_depth_areas.tif"
    local = cache_dir() / "tiles" / relative
    return str(local) if local.exists() else f"/vsicurl/{BASE_URL}/{relative}"


# --- per-pixel overlap ------------------------------------------------------------

def _read(path: str, bounds) -> tuple[np.ndarray, Any]:
    with rasterio.open(path) as dataset:
        exact = from_bounds(*bounds, dataset.transform)
        # Whole pixels covering the bounds: floor the start, ceil the end.
        col0, row0 = math.floor(exact.col_off), math.floor(exact.row_off)
        window = Window(col0, row0, math.ceil(exact.col_off + exact.width) - col0, math.ceil(exact.row_off + exact.height) - row0)
        array = dataset.read(1, window=window, boundless=True, fill_value=dataset.nodata if dataset.nodata is not None else 0)
        return array, dataset.window_transform(window)


def _pixel_weights(parcel, transform, shape_: tuple[int, int], to_m) -> np.ndarray:
    """Area in m2 of each pixel that lies inside the parcel (exact polygon overlap)."""
    rows, cols = shape_
    xs = transform.c + transform.a * np.arange(cols + 1)
    ys = transform.f + transform.e * np.arange(rows + 1)
    boxes = shapely.box(
        xs[None, :-1].repeat(rows, 0), ys[1:, None].repeat(cols, 1),
        xs[None, 1:].repeat(rows, 0), ys[:-1, None].repeat(cols, 1),
    )
    overlap = shapely.intersection(boxes, parcel)
    return shapely.area(shapely.transform(overlap, to_m))


def _scenario(depth, weights, permanent, spurious) -> dict[str, Any]:
    on_parcel = weights > 0
    valid_depth = depth != NODATA_DEPTH
    is_permanent = permanent == 1
    flagged = spurious == 1
    flooded = on_parcel & valid_depth & (depth > 0) & ~is_permanent
    reliable = flooded & ~flagged
    area = lambda mask: float(weights[mask].sum())  # noqa: E731
    depths = depth[reliable]
    depth_weights = weights[reliable]
    return {
        "flooded_area_m2": round(area(flooded), 1),
        "flagged_flooded_area_m2": round(area(flooded & flagged), 1),
        "max_depth_m": round(float(depths.max()), 2) if depths.size else None,
        "mean_depth_m": round(float((depths * depth_weights).sum() / depth_weights.sum()), 2) if depths.size else None,
        "zero_depth_area_m2": round(area(on_parcel & valid_depth & (depth == 0) & ~is_permanent), 1),
        "no_modelled_inundation_area_m2": round(area(on_parcel & ~valid_depth & ~is_permanent), 1),
    }


def _hash(geojson_polygon: dict[str, Any]) -> str:
    canonical = json.dumps(geojson_polygon, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(f"{VERSION}:{RESULT_FORMAT}:{canonical}".encode()).hexdigest()[:32]


_cache_lock = threading.Lock()


def _cache_get(key: str) -> dict[str, Any] | None:
    try:
        return json.loads((cache_dir() / "results.json").read_text(encoding="utf-8")).get(key)
    except (FileNotFoundError, json.JSONDecodeError):
        return None


def _cache_put(key: str, value: dict[str, Any]) -> None:
    with _cache_lock:
        path = cache_dir() / "results.json"
        try:
            cache = json.loads(path.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError):
            cache = {}
        cache[key] = value
        path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False, suffix=".tmp") as handle:
            json.dump(cache, handle)
        Path(handle.name).replace(path)


def assess(geojson_polygon: dict[str, Any]) -> dict[str, Any]:
    """River-flood exposure of the parcel for every return period."""
    key = _hash(geojson_polygon)
    cached = _cache_get(key)
    if cached is not None:
        return {**cached, "cache": "reused"}

    parcel = shape(geojson_polygon)
    if not parcel.is_valid:
        parcel = shapely.make_valid(parcel)
    centre = parcel.centroid
    scale_lon = 111_320.0 * math.cos(math.radians(centre.y))

    def to_m(coords):
        out = coords.copy()
        out[:, 0] = (coords[:, 0] - centre.x) * scale_lon
        out[:, 1] = (coords[:, 1] - centre.y) * 110_574.0
        return out

    parcel_area = float(shapely.area(shapely.transform(parcel, to_m)))
    surroundings = flood_indicators.buffered(parcel, SURROUNDINGS_M)
    tiles = [(prefix, extent) for prefix, extent in tile_index() if extent.intersects(surroundings)]
    totals = {rp: {"flooded_area_m2": 0.0, "flagged_flooded_area_m2": 0.0, "zero_depth_area_m2": 0.0,
                   "no_modelled_inundation_area_m2": 0.0, "depths": [], "near_flooded_m2": 0.0} for rp in RETURN_PERIODS}
    assessed_area = permanent_area = flagged_area = 0.0
    near_land_area = 0.0  # surroundings area that was read and is not permanent water
    errors: list[str] = []

    for prefix, extent in tiles:
        piece = parcel.intersection(extent)
        near = surroundings.intersection(extent)
        if near.is_empty:
            continue
        bounds = near.bounds
        layers = [f"RP{rp}" for rp in RETURN_PERIODS] + ["permanent_water", "spurious"]
        try:
            with ThreadPoolExecutor(max_workers=len(layers)) as pool:
                arrays = dict(zip(layers, pool.map(lambda layer: _read(_layer_path(prefix, layer), bounds), layers)))
        except Exception as error:  # noqa: BLE001 - provider failure: this part stays unassessed
            errors.append(f"{prefix}: {error}")
            continue
        _, transform = arrays["RP100"]
        grid = arrays["RP100"][0].shape
        weights = _pixel_weights(piece, transform, grid, to_m) if not piece.is_empty else np.zeros(grid)
        near_weights = _pixel_weights(near, transform, grid, to_m)
        permanent, spurious = arrays["permanent_water"][0], arrays["spurious"][0]
        near_land_area += float(near_weights[permanent != 1].sum())
        assessed_area += float(weights.sum())
        permanent_area += float(weights[permanent == 1].sum())
        flagged_area += float(weights[spurious == 1].sum())
        for rp in RETURN_PERIODS:
            depth = arrays[f"RP{rp}"][0].astype("float64")
            part = _scenario(depth, weights, permanent, spurious)
            for name in ("flooded_area_m2", "flagged_flooded_area_m2", "zero_depth_area_m2", "no_modelled_inundation_area_m2"):
                totals[rp][name] += part[name]
            reliable = (weights > 0) & (depth != NODATA_DEPTH) & (depth > 0) & (permanent != 1) & (spurious != 1)
            totals[rp]["depths"].append((depth[reliable], weights[reliable]))
            totals[rp]["near_flooded_m2"] += float(near_weights[(depth != NODATA_DEPTH) & (depth > 0) & (permanent != 1)].sum())

    if not tiles:
        coverage_note = "No hazard-map tile covers this location (small islands and areas outside the modelled land domain)."
    else:
        coverage_note = None
    assessed_share = min(1.0, assessed_area / parcel_area) if parcel_area else 0.0
    if errors and assessed_area == 0:
        raise RiverFloodUnavailable("; ".join(errors)[:400])

    scenarios = []
    for rp in RETURN_PERIODS:
        t = totals[rp]
        depths = np.concatenate([d for d, _ in t["depths"]]) if t["depths"] else np.array([])
        weights = np.concatenate([w for _, w in t["depths"]]) if t["depths"] else np.array([])
        scenarios.append({
            "return_period_years": rp,
            "annual_exceedance_probability": round(1.0 / rp, 4),
            "flooded_area_m2": round(t["flooded_area_m2"], 1),
            "flooded_share_of_parcel": round(t["flooded_area_m2"] / parcel_area, 4) if parcel_area else None,
            "flagged_flooded_area_m2": round(t["flagged_flooded_area_m2"], 1),
            "max_depth_m": round(float(depths.max()), 2) if depths.size else None,
            "mean_depth_m": round(float((depths * weights).sum() / weights.sum()), 2) if depths.size else None,
            "zero_depth_area_m2": round(t["zero_depth_area_m2"], 1),
            "no_modelled_inundation_area_m2": round(t["no_modelled_inundation_area_m2"], 1),
            # Land within 500 m of the parcel (the parcel included) modelled as flooded.
            "surroundings_flooded_share": round(t["near_flooded_m2"] / near_land_area, 4) if near_land_area else None,
        })

    result = {
        "status": "assessed" if assessed_share >= 0.999 else "partial" if assessed_share > 0 else "not_modelled",
        "dataset": DATASET,
        "licence": LICENCE,
        "citation": CITATION,
        "resolution": "3 arc-seconds (~90 m)",
        "model": "LISFLOOD hydrology (GloFAS v4 reanalysis) + LISFLOOD-FP inundation; modelled scenarios, not observed events",
        "parcel_area_m2": round(parcel_area, 1),
        "assessed_share_of_parcel": round(assessed_share, 4),
        "permanent_water_area_m2": round(permanent_area, 1),
        "quality_flagged_area_m2": round(flagged_area, 1),
        "surroundings_m": SURROUNDINGS_M,
        "tiles": [prefix for prefix, _ in tiles],
        "scenarios": scenarios,
        "coverage_note": coverage_note,
        "errors": errors or None,
    }
    # Only complete results are reused; a partial read is retried next time.
    if not errors:
        _cache_put(key, result)
    return {**result, "cache": "new"}
