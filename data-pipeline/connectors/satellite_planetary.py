"""Real Sentinel-2 L2A observations via Microsoft Planetary Computer.

This is a genuine imagery path: it searches the public STAC catalogue, reads the
red/NIR/SWIR bands straight out of the Cloud-Optimized GeoTIFFs over the parcel
polygon, and masks cloud using the scene classification layer. No credentials are
required - the SAS token endpoint is anonymous - so it works where AppEEARS
cannot without Earthdata login.

What it produces is a LAND-COVER signal (NDVI, NDBI). It is not evidence of
investment, price movement or development approval.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import sqlite3
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

import numpy as np
import rasterio
import requests
import shapely
from rasterio.enums import Resampling
from rasterio.features import geometry_mask
from rasterio.mask import mask as rio_mask
from rasterio.transform import array_bounds
from rasterio.warp import transform_geom
from rasterio.windows import from_bounds

# Imported for its side effect too: bounded GDAL HTTP options and cloud-read settings
# (no directory listing on open, .tif only, block cache). Measured 2026-10-11 on the
# Kadapa test parcel: 17-23 s without them, 11.5-12.4 s with, identical observations.
from connectors import flood_indicators  # noqa: F401
from connectors.regions import data_root


LOGGER = logging.getLogger(__name__)

STAC_URL = "https://planetarycomputer.microsoft.com/api/stac/v1/search"
SAS_URL = "https://planetarycomputer.microsoft.com/api/sas/v1/token/sentinel-2-l2a"
COLLECTION = "sentinel-2-l2a"

# Sentinel-2 scene classification values that make a pixel unusable.
SCL_CLOUD_SHADOW = 3
SCL_CLOUD_MEDIUM = 8
SCL_CLOUD_HIGH = 9
SCL_CIRRUS = 10
SCL_SATURATED = 1
SCL_NO_DATA = 0
UNUSABLE_SCL = frozenset({SCL_NO_DATA, SCL_SATURATED, SCL_CLOUD_SHADOW, SCL_CLOUD_MEDIUM, SCL_CLOUD_HIGH, SCL_CIRRUS})

# A 10 m band gives 1 pixel per 100 m². Below this the mean is dominated by edge
# pixels bleeding in from neighbouring land, so the observation is not reported.
MIN_USABLE_PIXELS = 4
# Dates are compared with each other, so each must describe most of the same ground:
# a mean over the clear quarter of a parcel is not comparable with a mean over all of it.
MIN_CLEAR_FRACTION = 0.5
NATIVE_RESOLUTION_M = 10.0
# Processing baseline 04.00 (Jan 2022) onwards stores reflectance as DN = 10000 * rho + 1000
# (ESA BOA_ADD_OFFSET = -1000). Ignoring it biases every index towards zero.
BOA_OFFSET_DN = 1000.0
BASELINE_04_START = "2022-01-25"

# Scene selection: one observation per season anchor (quarterly, repeated each year), so every
# date has a same-season partner a year apart and the change test never compares monsoon with
# summer. max_observations caps the anchors; alternates are read only for anchors that fail.
ANCHORS_PER_YEAR = 4
ANCHOR_TOLERANCE_DAYS = 30
ALTERNATES_PER_ANCHOR = 2
LOW_CLOUD_PCT = 10.0
MAX_CATALOGUE_PAGES = 10  # 1,000 scenes; a 2-year window over one parcel has ~150
STAC_FIELDS = {
    "include": ["id", "properties.datetime", "properties.eo:cloud_cover", "properties.s2:processing_baseline",
                "assets.B04.href", "assets.B08.href", "assets.B11.href", "assets.SCL.href", "geometry"],
    "exclude": ["bbox", "links", "stac_extensions"],
}

# --- cache -----------------------------------------------------------------
# A processed Sentinel-2 scene never changes (reprocessing publishes a new item id),
# so its measurement over a given polygon is reusable indefinitely. The catalogue
# search is not: newly published scenes appear in recent windows, so it is reused
# only briefly. Bump ALGORITHM_VERSION whenever the observation maths or masking changes.
# 2: reflectance offset removed; SCL and B11 resampled onto the 10 m grid, so the cloud
# mask lines up and NDBI uses only clear pixels (v1 averaged SWIR over cloud too).
# 3: clear fraction counted against the parcel's whole footprint, so a tile edge cutting the
# parcel no longer reads as a fully clear view (VIT: tile T44PLV covered 36 of 134 pixels).
ALGORITHM_VERSION = "s2l2a-ndvi-ndbi-3"
RECENT_WINDOW_DAYS = 60
CATALOGUE_TTL_RECENT_S = 6 * 3600
CATALOGUE_TTL_HISTORICAL_S = 30 * 86400
CACHE_MAX_ROWS = {"scenes": 200_000, "catalogue": 2_000}


def polygon_fingerprint(polygon: dict[str, Any]) -> str:
    """Coordinates to 1e-7 degree (~1 cm): float noise collapses, distinct parcels do not."""
    rings = [[[round(float(x), 7), round(float(y), 7)] for x, y, *_ in ring] for ring in polygon["coordinates"]]
    return hashlib.sha256(json.dumps(rings).encode()).hexdigest()[:24]


class ResultCache:
    """SQLite store shared by threads and processes: WAL, a busy timeout, row caps."""

    def __init__(self, path: Path) -> None:
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as db:
            db.execute("PRAGMA journal_mode=WAL")
            for table in CACHE_MAX_ROWS:
                db.execute(f"CREATE TABLE IF NOT EXISTS {table} (key TEXT PRIMARY KEY, value TEXT NOT NULL, "
                           "stored_at REAL NOT NULL, used_at REAL NOT NULL)")

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.path, timeout=30)

    def get(self, table: str, key: str) -> tuple[Any, float] | None:
        with self._connect() as db:
            row = db.execute(f"SELECT value, stored_at FROM {table} WHERE key = ?", (key,)).fetchone()
            if row:
                db.execute(f"UPDATE {table} SET used_at = ? WHERE key = ?", (time.time(), key))
        return (json.loads(row[0]), row[1]) if row else None

    def put(self, table: str, key: str, value: Any) -> None:
        now = time.time()
        with self._connect() as db:
            db.execute(f"INSERT OR REPLACE INTO {table} VALUES (?, ?, ?, ?)", (key, json.dumps(value), now, now))

    def prune(self) -> None:
        """Evict least-recently-used rows beyond each table's cap."""
        with self._connect() as db:
            for table, cap in CACHE_MAX_ROWS.items():
                excess = db.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] - cap
                if excess > 0:
                    db.execute(f"DELETE FROM {table} WHERE key IN (SELECT key FROM {table} ORDER BY used_at LIMIT ?)",
                               (excess,))


def _cache() -> ResultCache | None:
    if os.getenv("SENTINEL_CACHE", "on").strip().lower() in {"off", "0", "false", "no"}:
        return None
    return ResultCache(data_root() / "satellite" / "sentinel2-cache.sqlite")


class SatelliteError(RuntimeError):
    """Raised when no usable imagery could be retrieved."""


# Scene reads in flight across the whole process. A collection that misses the evidence deadline
# keeps reading in the background (so a re-run finds its scenes cached); without a shared cap,
# back-to-back analyses stacked those reads until the link saturated and even geocoding and DEM
# reads failed (measured 2026-10-12: Planetary Computer 6-20 s per request, then 1 s once stopped).
_SCENE_SLOTS = threading.BoundedSemaphore(int(os.getenv("SENTINEL_MAX_CONCURRENT_SCENES", "8")))


def season_anchors(start: date, end: date, limit: int) -> tuple[list[date], int]:
    """Target dates for the observations, and the matching tolerance in days.

    Windows of about a year or more get quarterly anchors repeated each year from the
    start date, so each anchor has a same-season partner 365 days away. Shorter windows
    get evenly spaced anchors and no seasonal pairing is possible.
    """
    span = (end - start).days
    if span >= 330:
        anchors = [start + timedelta(days=365 * year + 45 + 91 * quarter)
                   for year in range(span // 365 + 1) for quarter in range(ANCHORS_PER_YEAR)]
        anchors = [anchor for anchor in anchors if anchor <= end]
        # Keep whole seasonal pairs at the most recent end when the cap bites.
        return anchors[-limit:], ANCHOR_TOLERANCE_DAYS
    count = max(1, limit)
    return ([start + timedelta(days=round(span * (index + 0.5) / count)) for index in range(count)],
            max(3, span // count))


class PlanetaryComputerClient:
    """Sentinel-2 L2A NDVI/NDBI for a parcel polygon."""

    source_reference = "Sentinel-2 L2A (Microsoft Planetary Computer)"
    is_demo = False

    _token: dict[str, Any] = {}
    _token_lock = threading.Lock()

    def __init__(self, *, max_cloud_cover: float | None = None, max_observations: int = 8) -> None:
        self.max_cloud_cover = (
            max_cloud_cover if max_cloud_cover is not None
            else float(os.getenv("SENTINEL_MAX_CLOUD_COVER", "35"))
        )
        self.max_observations = max_observations
        self.timeout = float(os.getenv("SENTINEL_TIMEOUT_SECONDS", "60"))
        self.last_diagnostics: dict[str, Any] = {}
        # time.monotonic() after which no new scene read starts: the caller's evidence deadline. Reads
        # already in flight finish and are cached; queued ones are dropped, not left to saturate the link.
        self.give_up_at: float | None = None

    # --- plumbing ---------------------------------------------------------

    def _sas_token(self) -> str:
        """Anonymous, short-lived signing token; cached until shortly before expiry."""
        with self._token_lock:
            cached = PlanetaryComputerClient._token
            if cached and cached["expires_at"] > time.time() + 60:
                return cached["token"]
            response = requests.get(SAS_URL, timeout=self.timeout)
            response.raise_for_status()
            payload = response.json()
            PlanetaryComputerClient._token = {
                "token": payload["token"],
                # The endpoint returns an ISO expiry; keep a conservative hour.
                "expires_at": time.time() + 3000,
            }
            return payload["token"]

    @staticmethod
    def _bbox(polygon: dict[str, Any]) -> list[float]:
        ring = polygon["coordinates"][0]
        lons = [position[0] for position in ring]
        lats = [position[1] for position in ring]
        return [min(lons), min(lats), max(lons), max(lats)]

    @staticmethod
    def _date_string(value: date | datetime | str) -> str:
        if isinstance(value, datetime):
            return value.date().isoformat()
        if isinstance(value, date):
            return value.isoformat()
        return str(value)[:10]

    def _search(self, polygon: dict[str, Any], start: str, end: str) -> tuple[list[dict[str, Any]], bool]:
        """Every catalogue page for the window, trimmed to what the reader needs, sorted by date.

        Returns (features, truncated). The API returns newest first, 100 per page; reading
        only the first page silently dropped the start of a two-year window.
        """
        body: dict[str, Any] = {
            "collections": [COLLECTION],
            "bbox": self._bbox(polygon),
            "datetime": f"{start}T00:00:00Z/{end}T23:59:59Z",
            "query": {"eo:cloud_cover": {"lt": self.max_cloud_cover}},
            "limit": 100,
            "fields": STAC_FIELDS,
        }
        url, features, truncated = STAC_URL, [], False
        for page in range(MAX_CATALOGUE_PAGES):
            response = requests.post(url, json=body, timeout=self.timeout)
            response.raise_for_status()
            payload = response.json()
            features += [
                {"id": item["id"],
                 "properties": {key: item["properties"].get(key)
                                for key in ("datetime", "eo:cloud_cover", "s2:processing_baseline")},
                 "assets": {band: {"href": item["assets"][band]["href"]} for band in ("B04", "B08", "B11", "SCL")},
                 "geometry": item.get("geometry")}
                for item in payload.get("features", [])
            ]
            following = next((link for link in payload.get("links", []) if link.get("rel") == "next"), None)
            if following is None:
                break
            if page == MAX_CATALOGUE_PAGES - 1:
                truncated = True
                break
            url = following.get("href") or STAC_URL
            body = {**body, **following["body"]} if following.get("merge") else following.get("body") or body
        features.sort(key=lambda item: (item["properties"]["datetime"], item["id"]))
        return features, truncated

    def _catalogue(self, cache: ResultCache | None, polygon: dict[str, Any], start: str, end: str):
        """(features, truncated, age in seconds or None when queried now). Only a successful search is stored."""
        key = hashlib.sha256(json.dumps(["planetary-computer", COLLECTION, self._bbox(polygon), start, end,
                                         self.max_cloud_cover, "all-pages", MAX_CATALOGUE_PAGES, "footprints"]).encode()).hexdigest()
        recent = date.fromisoformat(end) >= date.today() - timedelta(days=RECENT_WINDOW_DAYS)
        ttl = CATALOGUE_TTL_RECENT_S if recent else CATALOGUE_TTL_HISTORICAL_S
        hit = cache.get("catalogue", key) if cache else None
        if hit and time.time() - hit[1] < ttl:
            return hit[0]["features"], hit[0]["truncated"], time.time() - hit[1]
        features, truncated = self._search(polygon, start, end)
        if cache:
            cache.put("catalogue", key, {"features": features, "truncated": truncated})
        return features, truncated, None

    def _scene_key(self, item: dict[str, Any], polygon: dict[str, Any]) -> str:
        parameters = [ALGORITHM_VERSION, sorted(UNUSABLE_SCL), MIN_USABLE_PIXELS, "all_touched", "B04,B08,B11,SCL"]
        return hashlib.sha256(json.dumps([item["id"], polygon_fingerprint(polygon), parameters]).encode()).hexdigest()

    def _read_band(self, item: dict[str, Any], band: str, geometry: dict[str, Any], token: str):
        """A 10 m band cropped to the parcel: (masked array, its transform, the parcel's full pixel count).

        Masked = outside the parcel, or beyond the scene's raster. The full count is taken on the
        same grid but ignoring where the raster ends, so a tile edge cutting the parcel shows up.
        """
        href = f"{item['assets'][band]['href']}?{token}"
        with rasterio.open(href) as source:
            projected = transform_geom("EPSG:4326", source.crs, geometry)
            array, transform = rio_mask(source, [projected], crop=True, filled=False, all_touched=True)
            window = from_bounds(*shapely.geometry.shape(projected).bounds, source.transform)
            window = window.round_offsets(op="floor").round_lengths(op="ceil")
            footprint = geometry_mask([projected], out_shape=(int(window.height) + 1, int(window.width) + 1),
                                      transform=source.window_transform(window), all_touched=True, invert=True)
            return array[0], transform, int(footprint.sum())

    def _read_on_grid(self, item: dict[str, Any], band: str, transform, shape: tuple[int, int], token: str):
        """A 20 m band (B11, SCL) resampled onto the 10 m crop grid, so pixel (i, j) is the same ground in every band."""
        href = f"{item['assets'][band]['href']}?{token}"
        with rasterio.open(href) as source:
            west, south, east, north = array_bounds(shape[0], shape[1], transform)
            window = from_bounds(west, south, east, north, source.transform)
            return source.read(1, window=window, out_shape=shape, resampling=Resampling.nearest,
                               boundless=True, fill_value=0)

    # --- observations -----------------------------------------------------

    @staticmethod
    def _offset(item: dict[str, Any]) -> float:
        baseline = item["properties"].get("s2:processing_baseline")
        try:
            return BOA_OFFSET_DN if float(baseline) >= 4.0 else 0.0
        except (TypeError, ValueError):
            return BOA_OFFSET_DN if item["properties"]["datetime"][:10] >= BASELINE_04_START else 0.0

    def _observation(self, item: dict[str, Any], geometry: dict[str, Any], token: str) -> dict[str, Any] | None:
        """One cloud-screened NDVI/NDBI observation, or None when too few clear pixels."""
        # Each band is a few HTTP round trips, so the bands are read two at a time: B11 and SCL
        # need B04's grid. Measured 2026-10-12 (VIT, 7 scenes): 12-28 s per scene one band after another.
        with ThreadPoolExecutor(max_workers=2) as bands:
            nir_read = bands.submit(self._read_band, item, "B08", geometry, token)
            red, transform, footprint = self._read_band(item, "B04", geometry, token)
            swir_read = bands.submit(self._read_on_grid, item, "B11", transform, red.shape, token)
            scl = self._read_on_grid(item, "SCL", transform, red.shape, token)
            nir, swir = nir_read.result()[0], swir_read.result()

        inside = ~np.ma.getmaskarray(red)
        offset = self._offset(item)
        red_values, nir_values = np.ma.getdata(red).astype("float64"), np.ma.getdata(nir).astype("float64")
        swir_values = np.asarray(swir, dtype="float64")
        # DN 0 is no-data in every band; a cloud, shadow or no-data SCL class removes the pixel.
        usable = (inside & ~np.ma.getmaskarray(nir) & ~np.isin(scl, list(UNUSABLE_SCL))
                  & (red_values > 0) & (nir_values > 0) & (swir_values > 0))
        usable_count, total = int(usable.sum()), max(int(inside.sum()), footprint)
        if usable_count < MIN_USABLE_PIXELS:
            return None

        def reflectance(values):
            return np.maximum(values[usable] - offset, 1.0)  # dark water can dip below the offset

        r, n, s = reflectance(red_values), reflectance(nir_values), reflectance(swir_values)
        return {
            "date": item["properties"]["datetime"][:10],
            "ndvi": round(float(np.mean((n - r) / (n + r))), 4),
            "ndbi": round(float(np.mean((s - n) / (s + n))), 4),
            "usable_pixel_count": usable_count,
            "parcel_pixel_count": total,
            "cloud_coverage": round(float(item["properties"].get("eo:cloud_cover") or 0.0) / 100.0, 3),
            # Share of the parcel NOT seen clearly: cloud, no-data, or beyond the scene's edge.
            "parcel_cloud_fraction": round(1.0 - (usable_count / total), 3) if total else None,
            "scene_covers_fraction": round(int(inside.sum()) / total, 3) if total else None,
            "resolution_m": float(abs(transform.a)),
            "swir_resolution_m": 20.0,
            "reflectance_offset_dn": offset,
            "scene_id": item["id"],
        }

    @staticmethod
    def _usable(observation: dict[str, Any] | None) -> bool:
        return bool(observation) and (observation.get("parcel_cloud_fraction") or 0.0) <= 1.0 - MIN_CLEAR_FRACTION

    def get_change_series(
        self,
        geojson_polygon: dict[str, Any],
        date_from: date | datetime | str,
        date_to: date | datetime | str,
    ) -> list[dict[str, Any]]:
        """One cloud-screened observation per season anchor, as available."""
        start, end = self._date_string(date_from), self._date_string(date_to)
        cache = _cache()
        features, truncated, catalogue_age = self._catalogue(cache, geojson_polygon, start, end)
        anchors, tolerance = season_anchors(date.fromisoformat(start), date.fromisoformat(end), self.max_observations)
        self.last_diagnostics = {
            "catalogue_age_s": None if catalogue_age is None else round(catalogue_age),
            "scenes_matched": len(features),
            "catalogue_truncated": truncated,
            "max_cloud_cover_pct": self.max_cloud_cover,
            "collection": COLLECTION,
            "catalogue": "Microsoft Planetary Computer STAC",
            "algorithm_version": ALGORITHM_VERSION,
            "selection": f"one observation per season anchor ({len(anchors)} anchors, +/-{tolerance} days)",
            "anchors": [anchor.isoformat() for anchor in anchors],
            "min_usable_pixels": MIN_USABLE_PIXELS,
            "min_clear_fraction": MIN_CLEAR_FRACTION,
        }
        if not features:
            raise SatelliteError(
                f"No Sentinel-2 L2A scene under {self.max_cloud_cover:.0f}% cloud "
                f"covers this parcel between {start} and {end}."
            )

        # Only scenes whose data footprint contains the whole parcel: adjacent tiles overlap, and the
        # one that clips the parcel would be a partial view. Then low-cloud scenes first, then the closest.
        parcel = shapely.geometry.shape(geojson_polygon)
        covering = [item for item in features
                    if not item.get("geometry") or shapely.geometry.shape(item["geometry"]).contains(parcel)]
        self.last_diagnostics["scenes_not_covering_parcel"] = len(features) - len(covering)

        def ranked(anchor: date) -> list[dict[str, Any]]:
            near = [item for item in covering
                    if abs((date.fromisoformat(item["properties"]["datetime"][:10]) - anchor).days) <= tolerance]
            return sorted(near, key=lambda item: (
                (item["properties"].get("eo:cloud_cover") or 0.0) > LOW_CLOUD_PCT,
                abs((date.fromisoformat(item["properties"]["datetime"][:10]) - anchor).days), item["id"]))

        options = {anchor: ranked(anchor) for anchor in anchors}
        measured: dict[str, dict[str, Any] | None] = {}  # scene id -> observation, or None when unusable
        counts = {"failed": 0, "from_cache": 0}

        def measure(items: list[dict[str, Any]]) -> None:
            to_read = []
            for item in items:
                hit = cache.get("scenes", self._scene_key(item, geojson_polygon)) if cache else None
                if hit is None:
                    to_read.append(item)
                    continue
                counts["from_cache"] += 1
                measured[item["id"]] = None if hit[0].get("unusable") else hit[0]
            if not to_read:
                return
            # Each scene is four HTTP range reads against blob storage, so scenes are read concurrently.
            token = self._sas_token()
            workers = min(len(to_read), int(os.getenv("SENTINEL_READ_WORKERS", "12")))
            def read(item):
                with _SCENE_SLOTS:
                    if self.give_up_at is not None and time.monotonic() > self.give_up_at:
                        raise TimeoutError("the evidence deadline passed before this scene was read")
                    return self._observation(item, geojson_polygon, token)

            with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
                futures = {pool.submit(read, item): item for item in to_read}
                for future in as_completed(futures):
                    item = futures[future]
                    try:
                        observation = future.result()
                    except Exception as error:  # one bad scene must not lose the series; never cached
                        LOGGER.warning("Sentinel-2 scene %s unreadable: %s", item.get("id"), error)
                        counts["failed"] += 1
                        continue
                    if cache:
                        cache.put("scenes", self._scene_key(item, geojson_polygon), observation or {"unusable": True})
                    measured[item["id"]] = observation

        def unique(items):
            seen: dict[str, dict[str, Any]] = {}
            for item in items:
                if item["id"] not in measured:
                    seen.setdefault(item["id"], item)
            return list(seen.values())

        # Wave 1: the best candidate for every anchor. Wave 2, only where that failed: alternates.
        measure(unique(candidates[0] for candidates in options.values() if candidates))
        missing = [anchor for anchor, candidates in options.items()
                   if not any(self._usable(measured.get(item["id"])) for item in candidates[:1])]
        if self.give_up_at is None or time.monotonic() < self.give_up_at:
            measure(unique(item for anchor in missing for item in options[anchor][1:1 + ALTERNATES_PER_ANCHOR]))
        if cache:
            cache.prune()

        observations: list[dict[str, Any]] = []
        used_dates: set[str] = set()
        for anchor, candidates in options.items():
            for item in candidates[:1 + ALTERNATES_PER_ANCHOR]:
                observation = measured.get(item["id"])
                if self._usable(observation) and observation["date"] not in used_dates:
                    observations.append({**observation, "anchor_date": anchor.isoformat()})
                    used_dates.add(observation["date"])
                    break
        # Scene id breaks date ties, so the series never depends on which read finished first.
        observations.sort(key=lambda row: (row["date"], row["scene_id"]))

        read = [value for value in measured.values()]
        self.last_diagnostics.update({
            "scenes_read": len(read) + counts["failed"],
            "observations_kept": len(observations),
            "observations_rejected": sum(1 for value in read if not self._usable(value)),
            "rejected_too_few_clear_pixels": sum(1 for value in read if value is None),
            "rejected_below_clear_fraction": sum(1 for value in read if value is not None and not self._usable(value)),
            "observations_failed": counts["failed"],
            "scenes_not_covering_parcel": self.last_diagnostics["scenes_not_covering_parcel"],
            "scenes_from_cache": counts["from_cache"],
            "anchors_without_observation": [anchor.isoformat() for anchor, candidates in options.items()
                                            if not any(row["anchor_date"] == anchor.isoformat() for row in observations)],
        })
        if not observations:
            raise SatelliteError(
                f"{len(features)} scene(s) matched but none had at least {MIN_CLEAR_FRACTION:.0%} of the parcel "
                f"cloud-free (and {MIN_USABLE_PIXELS}+ clear pixels)"
                + (f"; {counts['failed']} could not be read." if counts["failed"] else ".")
            )
        return observations

    def search_available_dates(self, geojson_polygon, date_from, date_to) -> list[dict[str, Any]]:
        return [
            {"date": row["date"], "cloud_coverage": row["cloud_coverage"]}
            for row in self.get_change_series(geojson_polygon, date_from, date_to)
        ]

    def get_ndvi_ndbi(self, geojson_polygon, observation_date) -> dict[str, Any]:
        day = self._date_string(observation_date)
        rows = self.get_change_series(geojson_polygon, day, day)
        return rows[0] if rows else {"date": day, "ndvi": None, "ndbi": None, "usable_pixel_count": 0}
