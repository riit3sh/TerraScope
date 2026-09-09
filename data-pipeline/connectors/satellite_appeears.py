"""NASA AppEEARS satellite connector for TerraScope's local demo.

AppEEARS is asynchronous: TerraScope submits one area task for the requested
polygon and date range, polls it, then computes polygon-masked NDVI/NDBI from
the returned HLS GeoTIFF layers. Product and layer names are configurable
because they depend on the AppEEARS catalog available to an Earthdata user.
"""

from __future__ import annotations

import hashlib
import io
import json
import logging
import os
import re
import time
import zipfile
import base64
from datetime import date, datetime
from pathlib import Path
from typing import Any

import numpy as np
import requests

from connectors.osm_infrastructure import InfrastructureClient

try:
    import rasterio
    from rasterio.mask import mask as raster_mask
except ImportError:  # pragma: no cover - gives a clearer message at runtime
    rasterio = None
    raster_mask = None


LOGGER = logging.getLogger(__name__)


class AppEEARSClient:
    """Small, debuggable AppEEARS client implementing the satellite connector contract."""

    source_reference = "NASA AppEEARS HLS"
    API_URL = os.getenv("NASA_APPEEARS_API_URL", "https://appeears.earthdatacloud.nasa.gov/api").rstrip("/")
    CACHE_PATH = Path(os.getenv("TERRASCOPE_SATELLITE_CACHE_PATH", ".cache/terrascope_satellite.json"))

    def __init__(self) -> None:
        self.username = os.getenv("NASA_APPEEARS_USERNAME", "").strip()
        self.password = os.getenv("NASA_APPEEARS_PASSWORD", "")
        self.static_token = os.getenv("NASA_APPEEARS_TOKEN", "")
        self.product = os.getenv("NASA_APPEEARS_PRODUCT", "HLSS30.020")
        self.layers = {
            "b04": os.getenv("NASA_APPEEARS_B04_LAYER", "B04"),
            "b08": os.getenv("NASA_APPEEARS_B08_LAYER", "B08"),
            "b11": os.getenv("NASA_APPEEARS_B11_LAYER", "B11"),
        }
        cloud_layer = os.getenv("NASA_APPEEARS_CLOUD_LAYER", "").strip()
        if cloud_layer:
            self.layers["cloud"] = cloud_layer
        self.demo_fallback = os.getenv("SATELLITE_DEMO_FALLBACK", "true").strip().lower() in {"1", "true", "yes", "on"}
        configured_poll_seconds = float(os.getenv("NASA_APPEEARS_POLL_SECONDS", "10"))
        configured_max_wait_seconds = float(os.getenv("NASA_APPEEARS_MAX_WAIT_SECONDS", "150"))
        # Local demos must not block the UI on an asynchronous public task that may never finish.
        # Set SATELLITE_DEMO_FALLBACK=false to opt into the full configured live wait.
        self.poll_seconds = min(configured_poll_seconds, 5.0) if self.demo_fallback else configured_poll_seconds
        self.max_wait_seconds = min(configured_max_wait_seconds, 30.0) if self.demo_fallback else configured_max_wait_seconds
        # An explicitly supplied AppEEARS bearer token takes precedence over login credentials.
        self._token: str | None = self.static_token or None
        self._session = requests.Session()
        self._cache: dict[str, Any] = self._load_cache()

    @staticmethod
    def _date_string(value: date | datetime | str) -> str:
        if isinstance(value, datetime):
            return value.date().isoformat()
        if isinstance(value, date):
            return value.isoformat()
        return date.fromisoformat(str(value)[:10]).isoformat()

    @staticmethod
    def _validate_polygon(polygon: dict[str, Any]) -> None:
        InfrastructureClient._validate_polygon(polygon)

    def _load_cache(self) -> dict[str, Any]:
        try:
            return json.loads(self.CACHE_PATH.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError):
            return {}

    def _save_cache(self) -> None:
        self.CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.CACHE_PATH.with_suffix(".tmp")
        temporary.write_text(json.dumps(self._cache), encoding="utf-8")
        temporary.replace(self.CACHE_PATH)

    def _cache_key(self, polygon: dict[str, Any], start: str, end: str) -> str:
        payload = {
            "polygon": polygon,
            "date_from": start,
            "date_to": end,
            "product": self.product,
            "layers": self.layers,
            "resolution": "native-hls",
        }
        return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()

    def _authenticate(self, force: bool = False) -> str:
        if self.static_token:
            if force:
                raise RuntimeError("AppEEARS bearer token was rejected (401). Generate a fresh token from AppEEARS and update NASA_APPEEARS_TOKEN.")
            return self.static_token
        if self._token and not force:
            return self._token
        if not self.username or not self.password:
            raise RuntimeError(
                "AppEEARS credentials missing. Set NASA_APPEEARS_USERNAME and NASA_APPEEARS_PASSWORD "
                "or NASA_APPEEARS_TOKEN."
            )
        basic = base64.b64encode(f"{self.username}:{self.password}".encode("utf-8")).decode("ascii")
        response = self._session.post(
            f"{self.API_URL}/login",
            data="grant_type=client_credentials",
            headers={
                "Authorization": f"Basic {basic}",
                "Content-Type": "application/x-www-form-urlencoded;charset=UTF-8",
                "Accept": "application/json",
            },
            timeout=20,
        )
        if response.status_code == 401:
            raise RuntimeError(
                "AppEEARS login rejected the credentials (401). Use the exact NASA Earthdata Login "
                "username and password that can sign in at appeears.earthdatacloud.nasa.gov; "
                "an Earthdata API token is not a password."
            )
        response.raise_for_status()
        payload = response.json()
        token = payload.get("token") or payload.get("access_token")
        if not token:
            raise RuntimeError("AppEEARS login succeeded but returned no token.")
        self._token = str(token)
        return self._token

    def _static_token_issuer(self) -> str | None:
        """Return a JWT issuer without logging or exposing the token itself."""
        if not self.static_token or self.static_token.count(".") != 2:
            return None
        try:
            encoded = self.static_token.split(".")[1]
            encoded += "=" * ((4 - len(encoded) % 4) % 4)
            payload = json.loads(base64.urlsafe_b64decode(encoded).decode("utf-8"))
            return str(payload.get("iss")) if payload.get("iss") else None
        except (ValueError, TypeError, json.JSONDecodeError, UnicodeDecodeError):
            return None

    def _request(self, method: str, path: str, **kwargs: Any) -> requests.Response:
        for attempt in range(4):
            token = self._authenticate()
            headers = dict(kwargs.pop("headers", {}))
            headers["Authorization"] = token if token.lower().startswith("bearer ") else f"Bearer {token}"
            response = self._session.request(method, f"{self.API_URL}/{path.lstrip('/')}", headers=headers, **kwargs)
            if response.status_code == 401 and attempt == 0:
                self._authenticate(force=True)
                continue
            if response.status_code == 429 and attempt < 3:
                delay = 2**attempt
                LOGGER.warning("AppEEARS rate limited; retrying in %ss", delay)
                time.sleep(delay)
                continue
            if response.status_code >= 400:
                detail = response.text[:500].replace("\n", " ")
                raise RuntimeError(f"AppEEARS request {method} {path} returned HTTP {response.status_code}: {detail}")
            return response
        raise RuntimeError(f"AppEEARS request failed after retries: {method} {path}")

    @staticmethod
    def _find_value(payload: Any, names: tuple[str, ...]) -> Any:
        if isinstance(payload, dict):
            for name in names:
                if name in payload:
                    return payload[name]
            for value in payload.values():
                found = AppEEARSClient._find_value(value, names)
                if found is not None:
                    return found
        elif isinstance(payload, list):
            for value in payload:
                found = AppEEARSClient._find_value(value, names)
                if found is not None:
                    return found
        return None

    def _submit_task(self, polygon: dict[str, Any], start: str, end: str) -> str:
        self._validate_polygon(polygon)
        layers = [{"product": self.product, "layer": layer} for layer in self.layers.values()]
        body = {
            "task_type": "area",
            "task_name": f"terrascope-{hashlib.sha1(json.dumps(polygon, sort_keys=True).encode()).hexdigest()[:10]}",
            "params": {
                "dates": [{
                    "startDate": date.fromisoformat(start).strftime("%m-%d-%Y"),
                    "endDate": date.fromisoformat(end).strftime("%m-%d-%Y"),
                }],
                "layers": layers,
                "output": {"projection": "geographic", "format": {"type": "geotiff"}},
                "geo": {
                    "type": "FeatureCollection",
                    "features": [{"type": "Feature", "properties": {}, "geometry": polygon}],
                },
            },
        }
        payload = self._request("POST", "/task", json=body, timeout=30).json()
        task_id = payload[0] if isinstance(payload, list) and payload and isinstance(payload[0], (str, int)) else None
        task_id = task_id or self._find_value(payload, ("task_id", "taskId", "id", "task"))
        if isinstance(task_id, dict):
            task_id = self._find_value(task_id, ("task_id", "taskId", "id"))
        if not task_id:
            raise RuntimeError(f"AppEEARS task submission returned no task id: {payload}")
        return str(task_id)

    def _wait_for_task(self, task_id: str) -> None:
        deadline = time.monotonic() + self.max_wait_seconds
        while time.monotonic() < deadline:
            payload = self._request("GET", f"/task/{task_id}", timeout=20).json()
            status = str(self._find_value(payload, ("status", "state")) or "").lower()
            if status in {"done", "complete", "completed", "success", "finished"}:
                return
            if status in {"error", "failed", "failure", "cancelled", "canceled"}:
                raise RuntimeError(f"AppEEARS task {task_id} failed: {payload}")
            time.sleep(self.poll_seconds)
        raise TimeoutError(f"AppEEARS task {task_id} did not finish within {self.max_wait_seconds:.0f}s.")

    def _download_files(self, task_id: str) -> list[tuple[str, bytes]]:
        bundle = self._request("GET", f"/bundle/{task_id}", timeout=30).json()
        files = bundle.get("files", bundle) if isinstance(bundle, dict) else bundle
        if isinstance(files, dict):
            files = list(files.values())
        outputs: list[tuple[str, bytes]] = []
        for item in files or []:
            if isinstance(item, str):
                file_id, filename = item, item
            else:
                file_id = item.get("file_id") or item.get("id") or item.get("file_name")
                filename = item.get("file_name") or item.get("filename") or str(file_id)
            if not file_id:
                continue
            response = self._request("GET", f"/bundle/{task_id}/{file_id}", timeout=60)
            outputs.append((str(filename), response.content))
        if not outputs:
            raise RuntimeError(f"AppEEARS task {task_id} completed without downloadable files.")
        return outputs

    @staticmethod
    def _date_from_filename(filename: str, fallback: str) -> str:
        match = re.search(r"(20\d{2})[._-]?(\d{2})[._-]?(\d{2})", filename)
        return "-".join(match.groups()) if match else fallback

    def _parse_outputs(self, polygon: dict[str, Any], outputs: list[tuple[str, bytes]], fallback_date: str) -> list[dict[str, Any]]:
        if rasterio is None or raster_mask is None:
            raise RuntimeError("The AppEEARS connector requires rasterio to read GeoTIFF outputs.")
        by_date: dict[str, dict[str, tuple[np.ndarray, np.ndarray]]] = {}
        for filename, content in outputs:
            members: list[tuple[str, bytes]]
            if zipfile.is_zipfile(io.BytesIO(content)):
                with zipfile.ZipFile(io.BytesIO(content)) as archive:
                    members = [(name, archive.read(name)) for name in archive.namelist() if name.lower().endswith((".tif", ".tiff"))]
            else:
                members = [(filename, content)] if filename.lower().endswith((".tif", ".tiff")) else []
            for member_name, member_content in members:
                lower = member_name.lower()
                layer = next((key for key, name in self.layers.items() if name.lower() in lower or key in lower), None)
                if layer not in {"b04", "b08", "b11"}:
                    continue
                day = self._date_from_filename(member_name, fallback_date)
                with rasterio.MemoryFile(member_content).open() as dataset:
                    values, _ = raster_mask(dataset, [polygon], crop=True, filled=False)
                    band = values[0]
                    if np.ma.isMaskedArray(band):
                        valid = (~band.mask) & np.isfinite(band.data)
                        array = np.asarray(band.data, dtype=float)
                    else:
                        array = np.asarray(band, dtype=float)
                        valid = np.isfinite(array)
                    if dataset.nodata is not None:
                        valid &= array != dataset.nodata
                    by_date.setdefault(day, {})[layer] = (array, valid)
        records: list[dict[str, Any]] = []
        for day in sorted(by_date):
            bands = by_date[day]
            if not all(name in bands for name in ("b04", "b08", "b11")):
                continue
            b04, m04 = bands["b04"]
            b08, m08 = bands["b08"]
            b11, m11 = bands["b11"]
            valid = m04 & m08 & m11
            denominator_ndvi = b08 + b04
            denominator_ndbi = b11 + b08
            valid &= denominator_ndvi != 0
            valid &= denominator_ndbi != 0
            if not np.any(valid):
                records.append({"date": day, "ndvi": None, "ndbi": None, "usable_pixel_count": 0, "cloud_coverage": None})
                continue
            ndvi = (b08[valid] - b04[valid]) / denominator_ndvi[valid]
            ndbi = (b11[valid] - b08[valid]) / denominator_ndbi[valid]
            finite = np.isfinite(ndvi) & np.isfinite(ndbi)
            records.append({
                "date": day,
                "ndvi": round(float(np.mean(ndvi[finite])), 6) if np.any(finite) else None,
                "ndbi": round(float(np.mean(ndbi[finite])), 6) if np.any(finite) else None,
                "usable_pixel_count": int(np.count_nonzero(finite)),
                "cloud_coverage": None,
            })
        return records

    def _fetch_series(self, polygon: dict[str, Any], start: str, end: str) -> list[dict[str, Any]]:
        key = self._cache_key(polygon, start, end)
        cached = self._cache.get(key)
        if cached is not None:
            return [dict(record) for record in cached]
        issuer = self._static_token_issuer()
        if issuer and "urs.earthdata.nasa.gov" in issuer:
            raise RuntimeError("The supplied NASA Earthdata URS token is not an AppEEARS task token; use AppEEARS login credentials for live satellite data.")
        task_id = self._submit_task(polygon, start, end)
        self._wait_for_task(task_id)
        series = self._parse_outputs(polygon, self._download_files(task_id), start)
        self._cache[key] = series
        self._save_cache()
        return [dict(record) for record in series]

    def search_available_dates(self, geojson_polygon: dict[str, Any], date_from: date | datetime | str, date_to: date | datetime | str) -> list[dict[str, Any]]:
        start, end = self._date_string(date_from), self._date_string(date_to)
        return [{"date": row["date"], "cloud_coverage": row.get("cloud_coverage")} for row in self._fetch_series(geojson_polygon, start, end)]

    def get_ndvi_ndbi(self, geojson_polygon: dict[str, Any], date: date | datetime | str) -> dict[str, Any]:
        day = self._date_string(date)
        rows = self._fetch_series(geojson_polygon, day, day)
        return rows[0] if rows else {"date": day, "ndvi": None, "ndbi": None, "usable_pixel_count": 0, "cloud_coverage": None}

    def get_change_series(self, geojson_polygon: dict[str, Any], date_from: date | datetime | str, date_to: date | datetime | str) -> list[dict[str, Any]]:
        start, end = self._date_string(date_from), self._date_string(date_to)
        try:
            rows = self._fetch_series(geojson_polygon, start, end)
        except Exception as exc:
            if not self.demo_fallback:
                raise
            LOGGER.warning("Live AppEEARS unavailable; using local demo satellite evidence: %s", exc)
            rows = []
            self.source_reference = "NASA AppEEARS HLS (unavailable)"
        if len(rows) <= 8:
            return rows
        indices = [round(i * (len(rows) - 1) / 7) for i in range(8)]
        return [rows[index] for index in indices]
