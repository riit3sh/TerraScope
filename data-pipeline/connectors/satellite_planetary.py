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

import logging
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime
from typing import Any

import numpy as np
import rasterio
import requests
from rasterio.mask import mask as rio_mask
from rasterio.warp import transform_geom


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
NATIVE_RESOLUTION_M = 10.0


class SatelliteError(RuntimeError):
    """Raised when no usable imagery could be retrieved."""


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

    def _search(self, polygon: dict[str, Any], start: str, end: str) -> list[dict[str, Any]]:
        body = {
            "collections": [COLLECTION],
            "bbox": self._bbox(polygon),
            "datetime": f"{start}T00:00:00Z/{end}T23:59:59Z",
            "query": {"eo:cloud_cover": {"lt": self.max_cloud_cover}},
            "limit": 100,
        }
        response = requests.post(STAC_URL, json=body, timeout=self.timeout)
        response.raise_for_status()
        features = response.json().get("features", [])
        features.sort(key=lambda item: item["properties"]["datetime"])
        return features

    def _read_band(self, item: dict[str, Any], band: str, geometry: dict[str, Any], token: str):
        href = f"{item['assets'][band]['href']}?{token}"
        with rasterio.open(href) as source:
            projected = transform_geom("EPSG:4326", source.crs, geometry)
            array, _ = rio_mask(source, [projected], crop=True, filled=False, all_touched=True)
            return array[0], source.res[0]

    # --- observations -----------------------------------------------------

    def _observation(self, item: dict[str, Any], geometry: dict[str, Any], token: str) -> dict[str, Any] | None:
        """One cloud-screened NDVI/NDBI observation, or None when unusable."""
        red, resolution = self._read_band(item, "B04", geometry, token)
        nir, _ = self._read_band(item, "B08", geometry, token)
        swir, swir_resolution = self._read_band(item, "B11", geometry, token)
        scl, _ = self._read_band(item, "SCL", geometry, token)

        # SCL is 20 m; repeat it to the 10 m grid so the mask lines up.
        if scl.shape != red.shape:
            scale_y = max(1, round(red.shape[0] / max(1, scl.shape[0])))
            scale_x = max(1, round(red.shape[1] / max(1, scl.shape[1])))
            scl = np.repeat(np.repeat(scl, scale_y, axis=0), scale_x, axis=1)
        scl = scl[: red.shape[0], : red.shape[1]]
        if scl.shape != red.shape:
            return None

        cloud = np.isin(np.ma.getdata(scl), list(UNUSABLE_SCL))
        usable = ~cloud & ~np.ma.getmaskarray(red) & ~np.ma.getmaskarray(nir)
        usable_count = int(usable.sum())
        total = int((~np.ma.getmaskarray(red)).sum())
        if usable_count < MIN_USABLE_PIXELS:
            return None

        red_values = np.ma.getdata(red)[usable].astype("float64")
        nir_values = np.ma.getdata(nir)[usable].astype("float64")
        ndvi = float(np.mean((nir_values - red_values) / np.maximum(nir_values + red_values, 1e-6)))

        # B11 is 20 m, so it is averaged over its own valid pixels rather than
        # pretending it shares the 10 m mask.
        swir_valid = np.ma.getdata(swir)[~np.ma.getmaskarray(swir)].astype("float64")
        if swir_valid.size == 0:
            return None
        ndbi = float(
            (np.mean(swir_valid) - np.mean(nir_values)) / max(np.mean(swir_valid) + np.mean(nir_values), 1e-6)
        )

        return {
            "date": item["properties"]["datetime"][:10],
            "ndvi": round(ndvi, 4),
            "ndbi": round(ndbi, 4),
            "usable_pixel_count": usable_count,
            "cloud_coverage": round(float(item["properties"].get("eo:cloud_cover") or 0.0) / 100.0, 3),
            "parcel_cloud_fraction": round(1.0 - (usable_count / total), 3) if total else None,
            "resolution_m": float(resolution),
            "swir_resolution_m": float(swir_resolution),
            "scene_id": item["id"],
        }

    def get_change_series(
        self,
        geojson_polygon: dict[str, Any],
        date_from: date | datetime | str,
        date_to: date | datetime | str,
    ) -> list[dict[str, Any]]:
        """Return evenly spread, cloud-screened observations for the polygon."""
        start, end = self._date_string(date_from), self._date_string(date_to)
        features = self._search(geojson_polygon, start, end)
        self.last_diagnostics = {
            "scenes_matched": len(features),
            "max_cloud_cover_pct": self.max_cloud_cover,
            "collection": COLLECTION,
            "catalogue": "Microsoft Planetary Computer STAC",
        }
        if not features:
            raise SatelliteError(
                f"No Sentinel-2 L2A scene under {self.max_cloud_cover:.0f}% cloud "
                f"covers this parcel between {start} and {end}."
            )

        token = self._sas_token()
        # Spread the attempts across the window so the series shows change over
        # time rather than a cluster from one season.
        step = max(1, len(features) // max(1, self.max_observations))
        candidates = features[::step][: self.max_observations + 4]

        # Each scene is four HTTP range reads against blob storage. Done one after
        # another this overran the pipeline's collection deadline and the whole
        # series was dropped, so scenes are read concurrently.
        observations: list[dict[str, Any]] = []
        rejected = 0
        workers = min(len(candidates), int(os.getenv("SENTINEL_READ_WORKERS", "8")))
        with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
            futures = {
                pool.submit(self._observation, item, geojson_polygon, token): item
                for item in candidates
            }
            for future in as_completed(futures):
                item = futures[future]
                try:
                    observation = future.result()
                except Exception as error:  # one bad scene must not lose the series
                    LOGGER.warning("Sentinel-2 scene %s unreadable: %s", item.get("id"), error)
                    rejected += 1
                    continue
                if observation is None:
                    rejected += 1
                    continue
                observations.append(observation)
        observations.sort(key=lambda row: row["date"])
        if len(observations) > self.max_observations:
            step = len(observations) / self.max_observations
            observations = [observations[int(index * step)] for index in range(self.max_observations)]

        self.last_diagnostics.update({
            "scenes_read": len(observations) + rejected,
            "observations_kept": len(observations),
            "observations_rejected": rejected,
            "min_usable_pixels": MIN_USABLE_PIXELS,
        })
        if not observations:
            raise SatelliteError(
                f"{len(features)} scene(s) matched but none yielded at least {MIN_USABLE_PIXELS} "
                "cloud-free pixels inside the parcel."
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
