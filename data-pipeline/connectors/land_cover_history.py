"""Annual land cover, 2017-2023, for the parcel and the land around it.

Impact Observatory / Esri 10 m Annual Land Use Land Cover v2 on Microsoft Planetary Computer
(CC BY 4.0, no account). Each year every 10 m pixel is classified (built area, crops, trees,
water, ...) by a model run over that year's Sentinel-2 imagery. TerraScope reads, per year:

- the parcel's own class shares (what the plot was each year);
- the built-area share within 1 km of the parcel edge, and between 1 and 3 km.

The trend in built area around the parcel is the development history the buy/wait decision
uses. It is a modelled classification: single pixels and single years can be wrong, so the
decision uses the least-squares trend over all years, never one year's jump.
"""

from __future__ import annotations

import math
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any

import numpy as np
import rasterio
import requests
import shapely
from rasterio.features import geometry_mask
from rasterio.warp import transform_geom
from rasterio.windows import from_bounds
from urllib3.util.retry import Retry

from connectors import flood_indicators  # GDAL HTTP settings and the versioned parcel-result cache

STAC_URL = "https://planetarycomputer.microsoft.com/api/stac/v1/search"
COLLECTION = "io-lulc-annual-v02"
TOKEN_URL = f"https://planetarycomputer.microsoft.com/api/sas/v1/token/{COLLECTION}"
DATASET = "Impact Observatory / Esri 10 m Annual Land Use Land Cover v2"
LICENCE = "CC BY 4.0 - Impact Observatory, Esri, Microsoft"
CLASSES = {1: "water", 2: "trees", 4: "flooded_vegetation", 5: "crops", 7: "built", 8: "bare", 9: "snow_ice", 11: "rangeland"}
NO_DATA, CLOUDS = 0, 10
NEAR_M, FAR_M = 1000.0, 3000.0
# A year is used only when this share of a zone was classified (not no-data or cloud).
MIN_COVERAGE = 0.5
MIN_TREND_YEARS = 4


# Planetary Computer answers bursts with 429 and a Retry-After of ~10 s; wait it out rather than lose the evidence.
_http = requests.Session()
_http.mount("https://", requests.adapters.HTTPAdapter(max_retries=Retry(
    total=3, backoff_factor=2, status_forcelist=(429, 502, 503, 504), allowed_methods=None, respect_retry_after_header=True)))
_token: dict[str, Any] = {}
_token_lock = threading.Lock()


def _sas_token() -> str:
    """One anonymous collection token for every tile, reused for 50 minutes (per-file signing hits 429)."""
    with _token_lock:
        if _token.get("expires_at", 0) <= time.time():
            response = _http.get(TOKEN_URL, timeout=30)
            response.raise_for_status()
            _token.update(token=response.json()["token"], expires_at=time.time() + 3000)
        return _token["token"]


def _search(polygon: dict[str, Any]) -> list[dict[str, Any]]:
    """Every tile-year whose footprint meets the parcel plus 3 km (a tile edge can cut the rings)."""
    west, south, east, north = shapely.geometry.shape(polygon).bounds
    lat_pad = FAR_M / 110_574
    lon_pad = FAR_M / (111_320 * math.cos(math.radians((south + north) / 2)))
    box = [west - lon_pad, south - lat_pad, east + lon_pad, north + lat_pad]
    response = _http.post(STAC_URL, json={"collections": [COLLECTION], "bbox": box, "limit": 100}, timeout=30)
    response.raise_for_status()
    return response.json().get("features", [])


def _tile_counts(item: dict[str, Any], polygon: dict[str, Any], token: str) -> tuple[int, dict[str, np.ndarray]]:
    """(year, class histogram per zone) for one tile-year. Pixels beyond the tile read as no-data."""
    with rasterio.open(f"{item['assets']['data']['href']}?{token}") as source:
        parcel = shapely.geometry.shape(transform_geom("EPSG:4326", source.crs, polygon))
        near, far = parcel.buffer(NEAR_M), parcel.buffer(FAR_M)
        window = from_bounds(*far.bounds, source.transform).round_offsets(op="floor").round_lengths(op="ceil")
        pixels = source.read(1, window=window, boundless=True, fill_value=NO_DATA)
        transform = source.window_transform(window)

    def inside(shape) -> np.ndarray:
        return geometry_mask([shapely.geometry.mapping(shape)], pixels.shape, transform, invert=True, all_touched=True)

    on_parcel, in_near, in_far = inside(parcel), inside(near), inside(far)
    zones = {"parcel": on_parcel, "near": in_near & ~on_parcel, "far": in_far & ~in_near}
    year = int(item["properties"]["start_datetime"][:4])
    return year, {name: np.bincount(pixels[mask], minlength=256) for name, mask in zones.items()}


def _trend(points: list[tuple[int, float]]) -> float | None:
    """Least-squares slope in percentage points per year, or None with too few years."""
    if len(points) < MIN_TREND_YEARS:
        return None
    years, shares = zip(*points)
    # + 0.0 turns the -0.0 that rounding leaves from float noise (a flat series gives ~-3e-15) into 0.0.
    return round(float(np.polyfit(years, [100 * share for share in shares], 1)[0]), 2) + 0.0


def summarise(counts: dict[int, dict[str, np.ndarray]], expected: dict[str, float]) -> dict[str, Any]:
    """Per-year shares and the built-area trends from per-year class histograms.

    ``expected`` is each zone's full pixel count (area / 100 m2), so a year where cloud or a
    tile edge hid most of a zone is dropped instead of describing a sliver of it.
    """
    parcel_years, surroundings = [], []
    for year in sorted(counts):
        row: dict[str, Any] = {"year": year}
        for zone in ("parcel", "near", "far"):
            histogram = counts[year][zone]
            classified = int(histogram.sum() - histogram[NO_DATA] - histogram[CLOUDS])
            coverage = classified / expected[zone] if expected[zone] else 0.0
            if classified == 0 or coverage < MIN_COVERAGE:
                row[zone] = None
                continue
            shares = {name: round(int(histogram[code]) / classified, 4) for code, name in CLASSES.items() if histogram[code]}
            row[zone] = {"shares": shares, "coverage": round(min(1.0, coverage), 3), "pixels": classified}
        if row["parcel"]:
            shares = row["parcel"]["shares"]
            parcel_years.append({"year": year, "dominant": max(shares, key=shares.get), **row["parcel"]})
        surroundings.append({
            "year": year,
            "built_share_within_1km": row["near"]["shares"].get("built", 0.0) if row["near"] else None,
            "built_share_1_to_3km": row["far"]["shares"].get("built", 0.0) if row["far"] else None,
        })

    def trend(key: str) -> dict[str, Any] | None:
        points = [(r["year"], r[key]) for r in surroundings if r[key] is not None]
        slope = _trend(points)
        if slope is None:
            return None
        return {"first_year": points[0][0], "first_share": points[0][1], "last_year": points[-1][0],
                "last_share": points[-1][1], "years_used": len(points), "slope_pts_per_year": slope}

    near_trend, far_trend = trend("built_share_within_1km"), trend("built_share_1_to_3km")
    return {
        "status": "assessed" if near_trend else "insufficient",
        "parcel": parcel_years,
        "surroundings": surroundings,
        "trend_within_1km": near_trend,
        "trend_1_to_3km": far_trend,
    }


def assess(polygon: dict[str, Any]) -> dict[str, Any]:
    """Land cover per year for the parcel and its surroundings, with built-area trends. Cached per polygon."""
    key = flood_indicators._result_cache_key("land-cover-history", polygon, {"collection": COLLECTION, "rings_m": [NEAR_M, FAR_M]})
    cached = flood_indicators._cached_result(key)
    if cached is not None:
        return {**cached, "cache": "reused"}
    items = _search(polygon)
    if not items:
        raise RuntimeError(f"No {COLLECTION} tiles cover this parcel.")
    token = _sas_token()
    with ThreadPoolExecutor(max_workers=8) as pool:
        tiles = list(pool.map(lambda item: _tile_counts(item, polygon, token), items))
    counts: dict[int, dict[str, np.ndarray]] = {}
    for year, zones in tiles:  # tiles never overlap, so a parcel split across two just adds up
        for zone, histogram in zones.items():
            counts.setdefault(year, {}).setdefault(zone, np.zeros(256, dtype=np.int64))
            counts[year][zone] += histogram
    result = summarise(counts, _expected_pixels(polygon))
    result.update({
        "dataset": DATASET, "collection": COLLECTION, "licence": LICENCE, "resolution_m": 10,
        "years": sorted(counts), "rings_m": [NEAR_M, FAR_M],
    })
    flood_indicators._cache_result(key, result)
    return {**result, "cache": "new"}


def _expected_pixels(polygon: dict[str, Any]) -> dict[str, float]:
    """Full 10 m pixel count of each zone, on a local metric projection of the parcel."""
    lon, lat = shapely.geometry.shape(polygon).centroid.coords[0]
    zone = int((lon + 180) // 6) + 1
    crs = f"EPSG:{32600 + zone if lat >= 0 else 32700 + zone}"
    parcel = shapely.geometry.shape(transform_geom("EPSG:4326", crs, polygon))
    near, far = parcel.buffer(NEAR_M), parcel.buffer(FAR_M)
    return {"parcel": parcel.area / 100, "near": (near.area - parcel.area) / 100, "far": (far.area - near.area) / 100}
