"""OpenStreetMap infrastructure and geometry helpers for TerraScope."""

from __future__ import annotations

import json
import logging
import math
import os
import tempfile
import threading
import time
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, as_completed, wait
from pathlib import Path
from typing import Any

import requests
from geographiclib.geodesic import Geodesic


LOGGER = logging.getLogger(__name__)


class InfrastructureError(RuntimeError):
    """Raised when an OSM service request or geometry operation fails."""


class InfrastructureClient:
    """Query nearby OSM infrastructure while respecting public API limits."""

    OVERPASS_URL = "https://overpass-api.de/api/interpreter"
    # The public instances congest unpredictably. Rather than sleeping on a
    # slow one, move to the next mirror; set OVERPASS_URLS to override.
    # Only whole-planet instances belong here: a regional extract answers fast
    # with zero elements outside its own country, which would be recorded as
    # 'no road found' rather than as the missing data it really is.
    OVERPASS_MIRRORS = (
        "https://overpass-api.de/api/interpreter",
        "https://overpass.private.coffee/api/interpreter",
        "https://overpass.kumi.systems/api/interpreter",
    )
    NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
    NOMINATIM_REVERSE_URL = "https://nominatim.openstreetmap.org/reverse"
    CACHE_TTL_SECONDS = 30 * 24 * 60 * 60
    MIN_REQUEST_INTERVAL_SECONDS = 1.0
    # Public Overpass instances throttle hard and time out under load; retry
    # the transient statuses rather than failing a whole parcel analysis.
    RETRY_STATUS_CODES = frozenset({429, 502, 503, 504})
    MAX_ATTEMPTS = 3
    # How long the primary gets alone before a mirror is started alongside it.
    HEDGE_DELAY_SECONDS = 5.0
    _LAST_REQUEST_AT: dict[str, float] = {}
    _THROTTLE_LOCK = threading.Lock()
    DEFAULT_USER_AGENT = "TerraScope/0.1.0 (local land due-diligence demo)"

    # Add a future category here; query construction and parsing remain unchanged.
    # Non-vehicular ways are excluded: a footpath 5 m away is not road access,
    # and in a city they were most of a multi-thousand-element response.
    _NON_ROAD_HIGHWAYS = (
        "footway|path|steps|cycleway|bridleway|corridor|pedestrian|platform"
        "|proposed|construction|raceway|escape|elevator|service|track"
    )
    TAGS = [
        {
            "name": "road",
            "selector": 'way[highway][highway!~"^(' + _NON_ROAD_HIGHWAYS + ')$"]',
            "tag_name": "highway",
            "tag_value": None,
            "type_tag": "highway",
            # Roads are dense, so a tighter radius finds the nearest one much
            # faster; beyond this the accessibility score is already at its floor.
            "radius_m": 1500.0,
        },
        {
            "name": "school",
            "selector": "nwr[amenity=school]",
            "tag_name": "amenity",
            "tag_value": "school",
            "type_tag": None,
            "radius_m": None,
        },
    ]

    def __init__(
        self,
        *,
        session: requests.Session | None = None,
        cache_path: str | Path | None = None,
        request_timeout: float = 25.0,
    ) -> None:
        self.session = session or requests.Session()
        self.request_timeout = request_timeout
        self.cache_path = Path(cache_path) if cache_path else self._default_cache_path()
        # Instance state is kept for compatibility; the throttle itself is shared
        # (see _LAST_REQUEST_AT) because a fresh client is built per analysis.
        self._last_overpass_request_at = 0.0
        self._last_nominatim_request_at = 0.0

    @staticmethod
    def _default_cache_path() -> Path:
        configured = os.getenv("TERRASCOPE_OSM_CACHE_PATH")
        if configured:
            return Path(configured)
        return Path(__file__).resolve().parents[1] / ".cache" / "osm_infrastructure.json"

    @staticmethod
    def _validate_polygon(geojson_polygon: dict[str, Any]) -> None:
        if not isinstance(geojson_polygon, dict) or geojson_polygon.get("type") != "Polygon":
            raise ValueError("geojson_polygon must be a GeoJSON Polygon geometry object.")
        coordinates = geojson_polygon.get("coordinates")
        if not isinstance(coordinates, list) or not coordinates or not isinstance(coordinates[0], list):
            raise ValueError("geojson_polygon must contain an exterior linear ring.")
        for ring in coordinates:
            if not isinstance(ring, list) or len(ring) < 4 or ring[0] != ring[-1]:
                raise ValueError("Every Polygon linear ring must have at least four positions and be closed.")
            for position in ring:
                if (
                    not isinstance(position, (list, tuple))
                    or len(position) < 2
                    or not all(isinstance(value, (int, float)) for value in position[:2])
                ):
                    raise ValueError("Polygon positions must be numeric [longitude, latitude] pairs.")

    @staticmethod
    def _representative_point(geojson_polygon: dict[str, Any]) -> tuple[float, float]:
        """Return a planar lon/lat centroid suitable as an Overpass search origin."""
        ring = geojson_polygon["coordinates"][0]
        vertices = ring[:-1]
        signed_area = 0.0
        centroid_lon = 0.0
        centroid_lat = 0.0
        for (lon_a, lat_a), (lon_b, lat_b) in zip(vertices, vertices[1:] + vertices[:1]):
            cross = lon_a * lat_b - lon_b * lat_a
            signed_area += cross
            centroid_lon += (lon_a + lon_b) * cross
            centroid_lat += (lat_a + lat_b) * cross
        if abs(signed_area) < 1e-12:
            return (
                sum(position[0] for position in vertices) / len(vertices),
                sum(position[1] for position in vertices) / len(vertices),
            )
        return centroid_lon / (3 * signed_area), centroid_lat / (3 * signed_area)

    @staticmethod
    def _haversine_meters(origin: tuple[float, float], point: tuple[float, float]) -> float:
        origin_lon, origin_lat = map(math.radians, origin)
        point_lon, point_lat = map(math.radians, point)
        delta_lat = point_lat - origin_lat
        delta_lon = point_lon - origin_lon
        value = math.sin(delta_lat / 2) ** 2 + math.cos(origin_lat) * math.cos(point_lat) * math.sin(delta_lon / 2) ** 2
        return 6_371_008.8 * 2 * math.atan2(math.sqrt(value), math.sqrt(max(0.0, 1 - value)))

    # Bumped whenever the measurement or the returned fields change, so stale
    # entries are ignored instead of serving results from the old method.
    CACHE_SCHEMA_VERSION = 2

    def _cache_key(self, representative_point: tuple[float, float], radius_meters: float) -> str:
        longitude, latitude = representative_point
        return (
            f"v{self.CACHE_SCHEMA_VERSION}:"
            f"{round(latitude, 3):.3f},{round(longitude, 3):.3f}:{float(radius_meters):.3f}"
        )

    def _read_cache(self) -> dict[str, Any]:
        try:
            return json.loads(self.cache_path.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            return {}

    def _write_cache(self, cache: dict[str, Any]) -> None:
        try:
            self.cache_path.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(
                "w", encoding="utf-8", dir=self.cache_path.parent, delete=False, prefix="osm-cache-", suffix=".tmp"
            ) as temporary:
                json.dump(cache, temporary, indent=2)
                temporary.write("\n")
                temporary_path = Path(temporary.name)
            temporary_path.replace(self.cache_path)
        except OSError as error:
            LOGGER.warning("Could not write OSM cache %s: %s", self.cache_path, error)

    def _wait_for_public_service(self, service: str) -> None:
        """Throttle one public service, shared across clients and threads."""
        key = "overpass" if service == "overpass" else "nominatim"
        with InfrastructureClient._THROTTLE_LOCK:
            last_request_at = InfrastructureClient._LAST_REQUEST_AT.get(key, 0.0)
            wait_seconds = self.MIN_REQUEST_INTERVAL_SECONDS - (time.monotonic() - last_request_at)
            if wait_seconds > 0:
                time.sleep(wait_seconds)
            InfrastructureClient._LAST_REQUEST_AT[key] = time.monotonic()
        setattr(self, "_last_overpass_request_at" if key == "overpass" else "_last_nominatim_request_at", time.monotonic())

    def _overpass_query(self, latitude: float, longitude: float, radius_meters: float) -> str:
        statements = [
            f"{tag['selector']}(around:{min(tag.get('radius_m') or radius_meters, radius_meters):g},"
            f"{latitude:.7f},{longitude:.7f});"
            for tag in self.TAGS
        ]
        # `out geom` returns every node of each way. `out center` returned only the
        # way's midpoint, so a 2 km road running past the plot was measured to its
        # middle rather than to the point where it actually passes.
        return "[out:json][timeout:25];(\n" + "\n".join(statements) + "\n);out geom tags;"

    def _overpass_endpoints(self) -> list[str]:
        configured = os.getenv("OVERPASS_URLS") or os.getenv("OVERPASS_URL")
        if configured:
            return [url.strip() for url in configured.split(",") if url.strip()]
        return list(self.OVERPASS_MIRRORS)

    def _fetch_overpass_once(self, endpoint: str, query: str, user_agent: str) -> dict[str, Any]:
        """One attempt against one endpoint. Raises on anything unusable."""
        response = self.session.get(
            endpoint,
            params={"data": query},
            headers={"User-Agent": user_agent},
            timeout=self.request_timeout,
        )
        if response.status_code in self.RETRY_STATUS_CODES:
            raise InfrastructureError(f"{endpoint}: HTTP {response.status_code}")
        if not response.ok:
            raise InfrastructureError(f"{endpoint}: HTTP {response.status_code}")
        payload = response.json()
        if not isinstance(payload, dict) or "elements" not in payload:
            raise InfrastructureError(f"{endpoint}: unexpected response shape")
        return payload

    def _request_overpass(self, query: str) -> dict[str, Any]:
        """Query Overpass, hedging across mirrors so one slow instance cannot stall.

        The primary gets a head start; if it has not answered within
        ``HEDGE_DELAY_SECONDS`` the next mirror is started alongside it and the
        first usable response wins. That keeps the common case to a single
        request while capping the worst case at roughly one timeout.
        """
        user_agent = os.getenv("TERRASCOPE_OSM_USER_AGENT", self.DEFAULT_USER_AGENT)
        endpoints = self._overpass_endpoints()
        self._wait_for_public_service("overpass")
        errors: list[str] = []
        with ThreadPoolExecutor(max_workers=len(endpoints)) as pool:
            futures = {}
            for index, endpoint in enumerate(endpoints):
                if index:
                    # Give the previous endpoint a head start before hedging.
                    done, _ = wait(set(futures), timeout=self.HEDGE_DELAY_SECONDS, return_when=FIRST_COMPLETED)
                    for future in done:
                        try:
                            return future.result()
                        except Exception as error:  # try the next mirror
                            errors.append(str(error))
                            futures.pop(future, None)
                futures[pool.submit(self._fetch_overpass_once, endpoint, query, user_agent)] = endpoint
            for future in as_completed(futures):
                try:
                    return future.result()
                except Exception as error:
                    errors.append(str(error))
        raise InfrastructureError(
            "Every Overpass endpoint was unavailable: " + "; ".join(errors[:3])
        )

    @staticmethod
    def _element_point(element: dict[str, Any]) -> tuple[float, float] | None:
        if isinstance(element.get("lat"), (int, float)) and isinstance(element.get("lon"), (int, float)):
            return float(element["lon"]), float(element["lat"])
        center = element.get("center")
        if isinstance(center, dict) and isinstance(center.get("lat"), (int, float)) and isinstance(center.get("lon"), (int, float)):
            return float(center["lon"]), float(center["lat"])
        return None

    @staticmethod
    def _closest_point_on_element(
        origin: tuple[float, float], element: dict[str, Any]
    ) -> tuple[float, tuple[float, float]] | None:
        """Nearest point on a way's geometry, in metres, with that point.

        Falls back to the element's own node or centre when no geometry is
        returned. Distances are still straight-line, not road-network travel.
        """
        origin_lon, origin_lat = origin
        geometry = element.get("geometry")
        if not isinstance(geometry, list) or len(geometry) < 2:
            point = InfrastructureClient._element_point(element)
            if point is None:
                return None
            return InfrastructureClient._haversine_meters(origin, point), point

        # Local equirectangular metres about the origin: over a few km the error
        # is far below the precision anyone should read into these distances.
        scale_lon = 111_320.0 * math.cos(math.radians(origin_lat))
        scale_lat = 110_574.0

        def to_xy(node: dict[str, Any]) -> tuple[float, float]:
            return ((node["lon"] - origin_lon) * scale_lon, (node["lat"] - origin_lat) * scale_lat)

        best_distance = float("inf")
        best_xy = (0.0, 0.0)
        previous = to_xy(geometry[0])
        for node in geometry[1:]:
            current = to_xy(node)
            ax, ay = previous
            bx, by = current
            dx, dy = bx - ax, by - ay
            if dx == 0.0 and dy == 0.0:
                candidate = (ax, ay)
            else:
                t = max(0.0, min(1.0, (-ax * dx - ay * dy) / (dx * dx + dy * dy)))
                candidate = (ax + t * dx, ay + t * dy)
            distance = math.hypot(candidate[0], candidate[1])
            if distance < best_distance:
                best_distance, best_xy = distance, candidate
            previous = current

        closest = (origin_lon + best_xy[0] / scale_lon, origin_lat + best_xy[1] / scale_lat)
        return best_distance, closest

    def nearest_amenities(
        self,
        geojson_polygon: dict[str, Any],
        radius_meters: float = 3000,
    ) -> dict[str, Any]:
        """Find nearest configured OSM categories from the polygon centroid."""
        self._validate_polygon(geojson_polygon)
        if radius_meters <= 0:
            raise ValueError("radius_meters must be greater than zero.")
        representative_point = self._representative_point(geojson_polygon)
        key = self._cache_key(representative_point, radius_meters)
        cache = self._read_cache()
        cached = cache.get(key)
        if isinstance(cached, dict) and time.time() - float(cached.get("cached_at", 0)) < self.CACHE_TTL_SECONDS:
            return dict(cached.get("value", {}))

        query = self._overpass_query(representative_point[1], representative_point[0], radius_meters)
        payload = self._request_overpass(query)
        # Keep the matched element's position: the map plots real amenity
        # locations rather than decorative markers at made-up offsets.
        nearest: dict[str, tuple[float, str | None, tuple[float, float], dict[str, Any]]] = {}
        for element in payload.get("elements", []):
            if not isinstance(element, dict):
                continue
            tags = element.get("tags", {})
            if not isinstance(tags, dict):
                continue
            measured = self._closest_point_on_element(representative_point, element)
            if measured is None:
                continue
            distance, point = measured
            if distance > radius_meters:
                continue
            for tag in self.TAGS:
                tag_value = tags.get(tag["tag_name"])
                if tag_value is None or (tag["tag_value"] is not None and tag_value != tag["tag_value"]):
                    continue
                category = tag["name"]
                category_type = str(tag_value) if tag["type_tag"] else None
                if category not in nearest or distance < nearest[category][0]:
                    nearest[category] = (distance, category_type, point, tags)

        road_tags = nearest["road"][3] if "road" in nearest else {}
        school_tags = nearest["school"][3] if "school" in nearest else {}
        # OpenStreetMap can say a way passes nearby. It cannot say the parcel has a
        # legal right of way onto it, or that any physical connection exists, so
        # proximity is reported as proximity and access is left unverified.
        access_tag = road_tags.get("access")
        result = {
            "nearest_road_distance_m": round(nearest["road"][0], 2) if "road" in nearest else None,
            "nearest_road_type": nearest["road"][1] if "road" in nearest else None,
            "nearest_road_name": road_tags.get("name") or road_tags.get("ref"),
            "nearest_road_access_tag": access_tag,
            "nearest_road_surface": road_tags.get("surface"),
            "nearest_school_distance_m": round(nearest["school"][0], 2) if "school" in nearest else None,
            "nearest_school_name": school_tags.get("name"),
            "distance_measurement": "straight_line_to_nearest_point_on_osm_geometry",
            "road_access_verified": False,
            "road_access_note": (
                "Proximity only. This is the straight-line distance to the nearest point on an "
                "OpenStreetMap way, not a routed travel distance, and it is not evidence of a legal "
                "right of way or of a physical connection to the parcel."
                + (f" The way is tagged access={access_tag}." if access_tag else "")
            ),
            **{
                f"nearest_{category}_{axis}": (
                    round(nearest[category][2][index], 6) if category in nearest else None
                )
                for category in ("road", "school")
                # points are (longitude, latitude).
                for axis, index in (("lat", 1), ("lon", 0))
            },
        }
        cache[key] = {"cached_at": time.time(), "value": result}
        self._write_cache(cache)
        return dict(result)

    def geocode_address(self, address_text: str) -> list[dict[str, Any]]:
        """Explicitly geocode a user-submitted search string.

        Callers should invoke this only after an explicit search action, never
        from a keystroke handler or as an implicit part of parcel analysis.
        """
        address_text = address_text.strip()
        if not address_text:
            raise ValueError("address_text must not be empty.")
        user_agent = os.getenv("NOMINATIM_USER_AGENT")
        if not user_agent:
            raise InfrastructureError("NOMINATIM_USER_AGENT must be set before using geocoding.")
        self._wait_for_public_service("nominatim")
        try:
            response = self.session.get(
                self.NOMINATIM_URL,
                params={"q": address_text, "format": "json", "limit": 5},
                headers={"User-Agent": user_agent},
                timeout=self.request_timeout,
            )
            response.raise_for_status()
            payload = response.json()
        except requests.RequestException as error:
            raise InfrastructureError(f"Nominatim request failed: {error}") from error
        except ValueError as error:
            raise InfrastructureError("Nominatim returned invalid JSON.") from error
        if not isinstance(payload, list):
            raise InfrastructureError("Nominatim returned an unexpected response shape.")
        return [
            {
                "display_name": item.get("display_name"),
                "latitude": float(item["lat"]) if item.get("lat") is not None else None,
                "longitude": float(item["lon"]) if item.get("lon") is not None else None,
                "osm_type": item.get("osm_type"),
                "osm_id": item.get("osm_id"),
                "type": item.get("type"),
                "address": item.get("address", {}),
            }
            for item in payload
            if isinstance(item, dict)
        ]

    def reverse_geocode(self, lat: float, lon: float) -> dict[str, Any] | None:
        """Resolve a representative point into address context when needed."""
        if not -90 <= lat <= 90 or not -180 <= lon <= 180:
            raise ValueError("lat/lon are outside valid WGS84 ranges.")
        user_agent = os.getenv("NOMINATIM_USER_AGENT")
        if not user_agent:
            raise InfrastructureError("NOMINATIM_USER_AGENT must be set before using geocoding.")
        self._wait_for_public_service("nominatim")
        try:
            response = self.session.get(
                self.NOMINATIM_REVERSE_URL,
                params={"lat": lat, "lon": lon, "format": "jsonv2", "addressdetails": 1},
                headers={"User-Agent": user_agent},
                timeout=self.request_timeout,
            )
            response.raise_for_status()
            payload = response.json()
        except requests.RequestException as error:
            raise InfrastructureError(f"Nominatim reverse-geocode request failed: {error}") from error
        except ValueError as error:
            raise InfrastructureError("Nominatim reverse-geocode returned invalid JSON.") from error
        if not isinstance(payload, dict):
            return None
        return {
            "display_name": payload.get("display_name"),
            "latitude": float(payload["lat"]) if payload.get("lat") is not None else lat,
            "longitude": float(payload["lon"]) if payload.get("lon") is not None else lon,
            "address": payload.get("address", {}),
            "osm_type": payload.get("osm_type"),
            "osm_id": payload.get("osm_id"),
            "type": payload.get("type"),
        }

    @staticmethod
    def _ring_metrics(ring: list[list[float]]) -> tuple[float, float]:
        polygon = Geodesic.WGS84.Polygon()
        for longitude, latitude, *_ in ring:
            polygon.AddPoint(latitude, longitude)
        _, perimeter, area = polygon.Compute(False, True)
        return abs(float(area)), float(perimeter)

    def polygon_metrics(self, geojson_polygon: dict[str, Any]) -> dict[str, float]:
        """Return WGS84 geodesic area, acres, and boundary perimeter."""
        self._validate_polygon(geojson_polygon)
        rings = geojson_polygon["coordinates"]
        outer_area, outer_perimeter = self._ring_metrics(rings[0])
        hole_area = sum(self._ring_metrics(ring)[0] for ring in rings[1:])
        area_m2 = max(0.0, outer_area - hole_area)
        perimeter_m = outer_perimeter + sum(self._ring_metrics(ring)[1] for ring in rings[1:])
        return {
            "area_m2": round(area_m2, 3),
            "area_acres": round(area_m2 / 4046.8564224, 6),
            "perimeter_m": round(perimeter_m, 3),
        }


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
    client = InfrastructureClient()
    print(json.dumps({
        "polygon_metrics": client.polygon_metrics(pune_sample_polygon),
        "nearest_amenities": client.nearest_amenities(pune_sample_polygon),
    }, indent=2))
