"""Small, debuggable Sentinel-2 connector for the Copernicus Data Space.

The connector deliberately uses the CDSE REST APIs directly. It keeps the
response cache in memory so a demo process can repeat an analysis without
reprocessing an identical parcel/date request.
"""

from __future__ import annotations

import hashlib
import json
import logging
import math
import os
import time
from datetime import date, datetime, timedelta
from typing import Any, Iterator

import requests


LOGGER = logging.getLogger(__name__)


class SentinelHubError(RuntimeError):
    """Base error raised by the SentinelHub connector."""


class ParcelTooLargeError(SentinelHubError, ValueError):
    """Raised before a Process API request when its native output is too large."""


class SentinelHubClient:
    """Client for CDSE OAuth, STAC search, and Sentinel Hub Process requests."""

    TOKEN_URL = "https://identity.dataspace.copernicus.eu/auth/realms/CDSE/protocol/openid-connect/token"
    STAC_URL = "https://stac.dataspace.copernicus.eu/v1"
    PROCESS_URL = "https://sh.dataspace.copernicus.eu/api/v1/process"
    COLLECTION = "sentinel-2-l2a"
    CLOUD_THRESHOLD = 20
    NATIVE_RESOLUTION_M = 10
    MAX_OUTPUT_PIXELS = 512 * 512
    MAX_OUTPUT_DIMENSION = 1024
    TOKEN_SAFETY_SECONDS = 60

    def __init__(
        self,
        *,
        session: requests.Session | None = None,
        request_timeout: float = 60.0,
    ) -> None:
        self.session = session or requests.Session()
        self.request_timeout = request_timeout
        self._token: str | None = None
        self._token_expires_at = 0.0
        self._cache: dict[str, Any] = {}

    def _credentials(self) -> tuple[str, str]:
        client_id = os.getenv("SENTINELHUB_CLIENT_ID")
        client_secret = os.getenv("SENTINELHUB_CLIENT_SECRET")
        if not client_id or not client_secret:
            raise SentinelHubError(
                "Missing SENTINELHUB_CLIENT_ID or SENTINELHUB_CLIENT_SECRET environment variable."
            )
        return client_id, client_secret

    def _get_access_token(self, *, force_refresh: bool = False) -> str:
        if not force_refresh and self._token and time.time() < self._token_expires_at:
            return self._token

        client_id, client_secret = self._credentials()
        try:
            response = self.session.post(
                self.TOKEN_URL,
                data={
                    "grant_type": "client_credentials",
                    "client_id": client_id,
                    "client_secret": client_secret,
                },
                timeout=self.request_timeout,
            )
            response.raise_for_status()
            payload = response.json()
        except requests.RequestException as error:
            raise SentinelHubError(f"CDSE OAuth token request failed: {error}") from error
        except ValueError as error:
            raise SentinelHubError("CDSE OAuth token response was not valid JSON.") from error

        token = payload.get("access_token")
        if not token:
            raise SentinelHubError("CDSE OAuth token response did not contain access_token.")
        expires_in = float(payload.get("expires_in", 300))
        self._token = str(token)
        self._token_expires_at = time.time() + max(1, expires_in - self.TOKEN_SAFETY_SECONDS)
        return self._token

    def _request_json(
        self,
        method: str,
        url: str,
        *,
        json_body: dict[str, Any] | None = None,
        authenticated: bool = True,
    ) -> Any:
        """Request JSON with one 401 refresh and up to three 429 retries."""
        refreshed = False
        rate_limit_retries = 0

        while True:
            headers = {"Accept": "application/json"}
            if authenticated:
                headers["Authorization"] = f"Bearer {self._get_access_token(force_refresh=refreshed)}"
            try:
                response = self.session.request(
                    method,
                    url,
                    json=json_body,
                    headers=headers,
                    timeout=self.request_timeout,
                )
            except requests.RequestException as error:
                raise SentinelHubError(f"Request to {url} failed: {error}") from error

            if response.status_code == 401 and authenticated and not refreshed:
                LOGGER.warning("CDSE returned 401; refreshing the access token and retrying once.")
                self._token = None
                refreshed = True
                continue

            if response.status_code == 429 and rate_limit_retries < 3:
                delay = 2**rate_limit_retries
                rate_limit_retries += 1
                LOGGER.warning(
                    "CDSE rate limited %s; retry %d/3 in %ss.",
                    url,
                    rate_limit_retries,
                    delay,
                )
                time.sleep(delay)
                continue

            if response.status_code == 413:
                raise ParcelTooLargeError(
                    "The Process API rejected this parcel as too large. Please draw a smaller analysis parcel."
                )

            if not response.ok:
                detail = response.text[:500].replace("\n", " ")
                raise SentinelHubError(f"CDSE request failed ({response.status_code}) at {url}: {detail}")

            try:
                return response.json()
            except ValueError as error:
                raise SentinelHubError(f"CDSE returned non-JSON data from {url}.") from error

    @staticmethod
    def _validate_polygon(geojson_polygon: dict[str, Any]) -> None:
        if not isinstance(geojson_polygon, dict) or geojson_polygon.get("type") != "Polygon":
            raise ValueError("geojson_polygon must be a GeoJSON Polygon geometry object.")
        coordinates = geojson_polygon.get("coordinates")
        if not isinstance(coordinates, list) or not coordinates or not isinstance(coordinates[0], list):
            raise ValueError("geojson_polygon must contain at least one Polygon linear ring.")
        ring = coordinates[0]
        if len(ring) < 4 or ring[0] != ring[-1]:
            raise ValueError("The Polygon's exterior ring must contain at least four positions and be closed.")
        if any(
            not isinstance(position, (list, tuple))
            or len(position) < 2
            or not all(isinstance(value, (int, float)) for value in position[:2])
            for position in ring
        ):
            raise ValueError("Polygon positions must be numeric [longitude, latitude] pairs.")

    @staticmethod
    def _date_string(value: date | datetime | str) -> str:
        if isinstance(value, datetime):
            return value.date().isoformat()
        if isinstance(value, date):
            return value.isoformat()
        try:
            return date.fromisoformat(value[:10]).isoformat()
        except (TypeError, ValueError) as error:
            raise ValueError(f"Invalid ISO date: {value!r}") from error

    @staticmethod
    def _polygon_hash(geojson_polygon: dict[str, Any]) -> str:
        canonical = json.dumps(geojson_polygon, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    def _cache_key(
        self,
        geojson_polygon: dict[str, Any],
        date_from: str,
        date_to: str,
        satellite_parameters: dict[str, Any],
    ) -> str:
        return json.dumps(
            {
                "polygon_hash": self._polygon_hash(geojson_polygon),
                "date_from": date_from,
                "date_to": date_to,
                "satellite_parameters": satellite_parameters,
            },
            sort_keys=True,
            separators=(",", ":"),
        )

    @staticmethod
    def _item_properties(item: dict[str, Any]) -> dict[str, Any]:
        properties = item.get("properties")
        return properties if isinstance(properties, dict) else {}

    def _stac_search(self, geojson_polygon: dict[str, Any], date_from: str, date_to: str) -> list[dict[str, Any]]:
        base_body: dict[str, Any] = {
            "collections": [self.COLLECTION],
            "datetime": f"{date_from}/{date_to}",
            "intersects": geojson_polygon,
            "limit": 100,
            "sortby": [{"field": "properties.datetime", "direction": "asc"}],
        }
        preferred_body = {
            **base_body,
            "query": {"eo:cloud_cover": {"lte": self.CLOUD_THRESHOLD}},
        }
        payload = self._request_json("POST", f"{self.STAC_URL}/search", json_body=preferred_body)
        features = payload.get("features", []) if isinstance(payload, dict) else []

        # If the preferred cloud filter finds nothing, retain cloudy observations
        # rather than claiming that there were no acquisitions at all.
        if not features:
            payload = self._request_json("POST", f"{self.STAC_URL}/search", json_body=base_body)
            features = payload.get("features", []) if isinstance(payload, dict) else []
        return [item for item in features if isinstance(item, dict)]

    def search_available_dates(
        self,
        geojson_polygon: dict[str, Any],
        date_from: date | datetime | str,
        date_to: date | datetime | str,
    ) -> list[dict[str, Any]]:
        """Return sorted Sentinel-2 acquisitions and useful STAC metadata."""
        self._validate_polygon(geojson_polygon)
        start = self._date_string(date_from)
        end = self._date_string(date_to)
        if start > end:
            raise ValueError("date_from must be on or before date_to.")

        records_by_date: dict[str, dict[str, Any]] = {}
        for item in self._stac_search(geojson_polygon, start, end):
            properties = self._item_properties(item)
            acquisition_datetime = properties.get("datetime") or item.get("datetime")
            if not acquisition_datetime:
                continue
            acquisition_date = str(acquisition_datetime)[:10]
            cloud = properties.get("eo:cloud_cover")
            record = {
                "date": acquisition_date,
                "datetime": acquisition_datetime,
                "cloud_coverage": float(cloud) if isinstance(cloud, (int, float)) else None,
                "item_id": item.get("id"),
                "collection": item.get("collection", self.COLLECTION),
            }
            current = records_by_date.get(acquisition_date)
            if current is None or (
                record["cloud_coverage"] is not None
                and (current["cloud_coverage"] is None or record["cloud_coverage"] < current["cloud_coverage"])
            ):
                records_by_date[acquisition_date] = record
        records = list(records_by_date.values())
        return sorted(records, key=lambda record: (record["date"], record["cloud_coverage"] is None, record["cloud_coverage"] or 0))

    def _estimate_output(self, geojson_polygon: dict[str, Any]) -> tuple[int, int, float, float]:
        ring = geojson_polygon["coordinates"][0]
        longitudes = [float(position[0]) for position in ring]
        latitudes = [float(position[1]) for position in ring]
        min_lon, max_lon = min(longitudes), max(longitudes)
        min_lat, max_lat = min(latitudes), max(latitudes)
        center_lat = (min_lat + max_lat) / 2
        meters_per_degree_lat = 111_320.0
        meters_per_degree_lon = max(1.0, meters_per_degree_lat * math.cos(math.radians(center_lat)))
        width_m = (max_lon - min_lon) * meters_per_degree_lon
        height_m = (max_lat - min_lat) * meters_per_degree_lat
        width = max(1, math.ceil(width_m / self.NATIVE_RESOLUTION_M))
        height = max(1, math.ceil(height_m / self.NATIVE_RESOLUTION_M))
        if width > self.MAX_OUTPUT_DIMENSION or height > self.MAX_OUTPUT_DIMENSION or width * height > self.MAX_OUTPUT_PIXELS:
            raise ParcelTooLargeError(
                "The parcel is too large for a native 10 m demo Process API request "
                f"({width}x{height} pixels estimated). Please draw a smaller analysis parcel."
            )
        resx = self.NATIVE_RESOLUTION_M / meters_per_degree_lon
        resy = self.NATIVE_RESOLUTION_M / meters_per_degree_lat
        return width, height, resx, resy

    @staticmethod
    def _evalscript() -> str:
        return """//VERSION=3
function setup() {
  return {
    input: ["B04", "B08", "B11", "SCL", "dataMask"],
    output: { id: "default", bands: 3, sampleType: SampleType.FLOAT32 }
  };
}

function evaluatePixel(sample) {
  if (sample.dataMask === 0 || [3, 8, 9, 10, 11].includes(sample.SCL)) {
    return [0, 0, 0];
  }
  let ndviDenominator = sample.B08 + sample.B04;
  let ndbiDenominator = sample.B11 + sample.B08;
  let ndvi = ndviDenominator === 0 ? 0 : (sample.B08 - sample.B04) / ndviDenominator;
  let ndbi = ndbiDenominator === 0 ? 0 : (sample.B11 - sample.B08) / ndbiDenominator;
  return [ndvi, ndbi, sample.dataMask];
}
"""

    @staticmethod
    def _iter_pixel_values(payload: Any) -> Iterator[tuple[float, float, float]]:
        if isinstance(payload, dict):
            if {"ndvi", "ndbi"}.issubset(payload):
                valid = payload.get("valid", payload.get("dataMask", 1))
                if all(isinstance(payload.get(key), (int, float)) for key in ("ndvi", "ndbi")):
                    yield float(payload["ndvi"]), float(payload["ndbi"]), float(valid or 0)
            for value in payload.values():
                yield from SentinelHubClient._iter_pixel_values(value)
            return
        if isinstance(payload, list):
            if len(payload) == 3 and all(isinstance(value, (int, float)) for value in payload):
                yield float(payload[0]), float(payload[1]), float(payload[2])
                return
            for value in payload:
                yield from SentinelHubClient._iter_pixel_values(value)

    def _process_indices(self, geojson_polygon: dict[str, Any], day: str) -> dict[str, Any]:
        width, height, resx, resy = self._estimate_output(geojson_polygon)
        next_day = (date.fromisoformat(day) + timedelta(days=1)).isoformat()
        request_body = {
            "input": {
                "bounds": {
                    "geometry": geojson_polygon,
                    "properties": {"crs": "http://www.opengis.net/def/crs/OGC/1.3/CRS84"},
                },
                "data": [
                    {
                        "type": self.COLLECTION,
                        "dataFilter": {
                            "timeRange": {"from": f"{day}T00:00:00Z", "to": f"{next_day}T00:00:00Z"},
                            "maxCloudCoverage": self.CLOUD_THRESHOLD,
                            "mosaickingOrder": "leastCC",
                        },
                    }
                ],
            },
            "output": {
                "resx": resx,
                "resy": resy,
                "width": width,
                "height": height,
                "responses": [{"identifier": "default", "format": {"type": "application/json"}}],
            },
            "evalscript": self._evalscript(),
        }
        payload = self._request_json("POST", self.PROCESS_URL, json_body=request_body)
        valid_pixels: list[tuple[float, float]] = []
        for ndvi, ndbi, data_mask in self._iter_pixel_values(payload):
            if data_mask <= 0 or not math.isfinite(ndvi) or not math.isfinite(ndbi):
                continue
            valid_pixels.append((ndvi, ndbi))
        if not valid_pixels:
            return {"date": day, "ndvi": None, "ndbi": None, "usable_pixel_count": 0}
        return {
            "date": day,
            "ndvi": round(sum(value[0] for value in valid_pixels) / len(valid_pixels), 6),
            "ndbi": round(sum(value[1] for value in valid_pixels) / len(valid_pixels), 6),
            "usable_pixel_count": len(valid_pixels),
        }

    def get_ndvi_ndbi(self, geojson_polygon: dict[str, Any], date: date | datetime | str) -> dict[str, Any]:
        """Return polygon-masked mean NDVI/NDBI for one acquisition date."""
        self._validate_polygon(geojson_polygon)
        day = self._date_string(date)
        parameters = {
            "collection": self.COLLECTION,
            "cloud_threshold": self.CLOUD_THRESHOLD,
            "native_resolution_m": self.NATIVE_RESOLUTION_M,
            "evalscript": "ndvi-ndbi-v1",
        }
        key = self._cache_key(geojson_polygon, day, day, parameters)
        if key not in self._cache:
            self._cache[key] = self._process_indices(geojson_polygon, day)
        return dict(self._cache[key])

    def get_change_series(
        self,
        geojson_polygon: dict[str, Any],
        date_from: date | datetime | str,
        date_to: date | datetime | str,
    ) -> list[dict[str, Any]]:
        """Sample up to eight representative cloud-aware observations."""
        self._validate_polygon(geojson_polygon)
        start = self._date_string(date_from)
        end = self._date_string(date_to)
        if start > end:
            raise ValueError("date_from must be on or before date_to.")
        parameters = {
            "collection": self.COLLECTION,
            "cloud_threshold": self.CLOUD_THRESHOLD,
            "native_resolution_m": self.NATIVE_RESOLUTION_M,
            "sample_count": 8,
        }
        key = self._cache_key(geojson_polygon, start, end, parameters)
        if key in self._cache:
            return [dict(record) for record in self._cache[key]]

        available = self.search_available_dates(geojson_polygon, start, end)
        if len(available) > 8:
            indices = [round(index * (len(available) - 1) / 7) for index in range(8)]
            selected = [available[index] for index in indices]
        else:
            selected = available

        series: list[dict[str, Any]] = []
        for observation in selected:
            metrics = self.get_ndvi_ndbi(geojson_polygon, observation["date"])
            series.append(
                {
                    "date": observation["date"],
                    "ndvi": metrics["ndvi"],
                    "ndbi": metrics["ndbi"],
                    "usable_pixel_count": metrics["usable_pixel_count"],
                    "cloud_coverage": observation["cloud_coverage"],
                }
            )
        self._cache[key] = series
        return [dict(record) for record in series]


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    pune_sample_polygon = {
        "type": "Polygon",
        "coordinates": [[
            [73.8567, 18.5204],
            [73.8582, 18.5204],
            [73.8582, 18.5218],
            [73.8567, 18.5218],
            [73.8567, 18.5204],
        ]],
    }
    client = SentinelHubClient()
    result = client.get_change_series(pune_sample_polygon, "2024-01-01", "2024-12-31")
    print(json.dumps(result, indent=2))
