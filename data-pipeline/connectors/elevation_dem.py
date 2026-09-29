"""Open-Elevation connector and coarse elevation-relative flood proxy."""

from __future__ import annotations

import json
import logging
import math
import time
from typing import Any

import requests


LOGGER = logging.getLogger(__name__)


# Below this absolute elevation a parcel is treated as lowland/deltaic, which
# carries flood exposure regardless of how it sits against nearby terrain.
LOWLAND_ELEVATION_M = 60.0
LOWLAND_MAX_POINTS = 35.0


class ElevationError(RuntimeError):
    """Raised when Open-Elevation cannot provide a usable result."""


class ElevationClient:
    """Retrieve representative elevation values for TerraScope demo parcels."""

    API_URL = "https://api.open-elevation.com/api/v1/lookup"
    REQUEST_TIMEOUT_SECONDS = 5.0
    RETRY_DELAY_SECONDS = 2.0

    def __init__(self, *, session: requests.Session | None = None) -> None:
        self.session = session or requests.Session()

    @staticmethod
    def _validate_coordinate(lat: float, lon: float) -> None:
        if not -90 <= lat <= 90:
            raise ValueError("lat must be between -90 and 90.")
        if not -180 <= lon <= 180:
            raise ValueError("lon must be between -180 and 180.")

    def get_elevation(self, lat: float, lon: float) -> float:
        """Return elevation in metres, retrying once after timeout or HTTP 5xx."""
        self._validate_coordinate(lat, lon)
        for attempt in range(2):
            try:
                response = self.session.get(
                    self.API_URL,
                    params={"locations": f"{lat:.7f},{lon:.7f}"},
                    timeout=self.REQUEST_TIMEOUT_SECONDS,
                )
            except requests.Timeout as error:
                if attempt == 0:
                    LOGGER.warning("Open-Elevation timed out; retrying in 2 seconds.")
                    time.sleep(self.RETRY_DELAY_SECONDS)
                    continue
                raise ElevationError("Open-Elevation timed out after one retry.") from error
            except requests.RequestException as error:
                raise ElevationError(f"Open-Elevation request failed: {error}") from error

            if response.status_code >= 500:
                if attempt == 0:
                    LOGGER.warning("Open-Elevation returned HTTP %s; retrying in 2 seconds.", response.status_code)
                    time.sleep(self.RETRY_DELAY_SECONDS)
                    continue
                raise ElevationError(f"Open-Elevation remained unavailable (HTTP {response.status_code}).")

            if not response.ok:
                raise ElevationError(f"Open-Elevation request failed with HTTP {response.status_code}.")
            try:
                payload = response.json()
            except ValueError as error:
                raise ElevationError("Open-Elevation returned invalid JSON.") from error

            results = payload.get("results") if isinstance(payload, dict) else None
            if not isinstance(results, list) or not results or not isinstance(results[0], dict):
                raise ElevationError("Open-Elevation response did not contain a result.")
            elevation = results[0].get("elevation")
            if not isinstance(elevation, (int, float)) or not math.isfinite(float(elevation)):
                raise ElevationError("Open-Elevation returned an invalid elevation value.")
            return float(elevation)

        raise ElevationError("Open-Elevation lookup failed.")

    def get_elevations(self, points: list[tuple[float, float]]) -> list[float | None]:
        """Look up many points in one request; unusable entries come back as None."""
        if not points:
            return []
        for latitude, longitude in points:
            self._validate_coordinate(latitude, longitude)
        locations = "|".join(f"{lat:.7f},{lon:.7f}" for lat, lon in points)
        try:
            response = self.session.get(
                self.API_URL, params={"locations": locations}, timeout=self.REQUEST_TIMEOUT_SECONDS * 3
            )
            response.raise_for_status()
            results = response.json().get("results")
        except (requests.RequestException, ValueError) as error:
            raise ElevationError(f"Open-Elevation batch lookup failed: {error}") from error
        if not isinstance(results, list):
            raise ElevationError("Open-Elevation batch response did not contain results.")
        values: list[float | None] = []
        for item in results:
            value = item.get("elevation") if isinstance(item, dict) else None
            values.append(
                float(value) if isinstance(value, (int, float)) and math.isfinite(float(value)) else None
            )
        return values

    def sample_terrain(
        self,
        lat: float,
        lon: float,
        radius_km: float = 5.0,
        rings: int = 2,
        per_ring: int = 8,
    ) -> dict[str, Any]:
        """Sample a ring of surrounding points to characterise the local terrain.

        The flood proxy needs something to compare the parcel against. Comparing
        it with its own elevation (the previous default) always produced exactly
        50, so every parcel scored identically. Sampling the land around it gives
        a real signal: sitting low in a basin reads differently from a ridge.
        """
        self._validate_coordinate(lat, lon)
        degrees_per_km_lat = 1.0 / 110.574
        degrees_per_km_lon = 1.0 / (111.320 * max(0.2, math.cos(math.radians(lat))))
        points: list[tuple[float, float]] = [(lat, lon)]
        for ring in range(1, rings + 1):
            distance = radius_km * ring / rings
            for step in range(per_ring):
                bearing = 2 * math.pi * step / per_ring
                sample_lat = lat + distance * math.cos(bearing) * degrees_per_km_lat
                sample_lon = lon + distance * math.sin(bearing) * degrees_per_km_lon
                if -90 <= sample_lat <= 90 and -180 <= sample_lon <= 180:
                    points.append((sample_lat, sample_lon))

        elevations = self.get_elevations(points)
        centre = elevations[0] if elevations else None
        neighbours = [value for value in elevations[1:] if value is not None]
        if centre is None or len(neighbours) < 4:
            raise ElevationError("Open-Elevation did not return enough surrounding samples.")
        ordered = sorted(neighbours)
        median = (
            ordered[len(ordered) // 2]
            if len(ordered) % 2
            else (ordered[len(ordered) // 2 - 1] + ordered[len(ordered) // 2]) / 2.0
        )
        return {
            "elevation_m": centre,
            "baseline_m": median,
            "sample_count": len(neighbours),
            "radius_km": radius_km,
            "min_m": ordered[0],
            "max_m": ordered[-1],
        }

    @staticmethod
    def _validate_polygon(geojson_polygon: dict[str, Any]) -> None:
        if not isinstance(geojson_polygon, dict) or geojson_polygon.get("type") != "Polygon":
            raise ValueError("geojson_polygon must be a GeoJSON Polygon geometry object.")
        coordinates = geojson_polygon.get("coordinates")
        if not isinstance(coordinates, list) or not coordinates or not isinstance(coordinates[0], list):
            raise ValueError("geojson_polygon must contain an exterior linear ring.")
        ring = coordinates[0]
        if len(ring) < 4 or ring[0] != ring[-1]:
            raise ValueError("The Polygon exterior ring must contain at least four positions and be closed.")
        for position in ring:
            if (
                not isinstance(position, (list, tuple))
                or len(position) < 2
                or not all(isinstance(value, (int, float)) for value in position[:2])
            ):
                raise ValueError("Polygon positions must be numeric [longitude, latitude] pairs.")

    @classmethod
    def polygon_centroid(cls, geojson_polygon: dict[str, Any]) -> tuple[float, float]:
        """Return the polygon centroid as ``(latitude, longitude)``."""
        cls._validate_polygon(geojson_polygon)
        vertices = geojson_polygon["coordinates"][0][:-1]
        signed_area = 0.0
        centroid_lon = 0.0
        centroid_lat = 0.0
        for (lon_a, lat_a), (lon_b, lat_b) in zip(vertices, vertices[1:] + vertices[:1]):
            cross = lon_a * lat_b - lon_b * lat_a
            signed_area += cross
            centroid_lon += (lon_a + lon_b) * cross
            centroid_lat += (lat_a + lat_b) * cross
        if abs(signed_area) < 1e-12:
            longitude = sum(position[0] for position in vertices) / len(vertices)
            latitude = sum(position[1] for position in vertices) / len(vertices)
        else:
            longitude = centroid_lon / (3 * signed_area)
            latitude = centroid_lat / (3 * signed_area)
        return float(latitude), float(longitude)

    def get_polygon_representative_elevation(self, geojson_polygon: dict[str, Any]) -> dict[str, Any]:
        """Get elevation at the centroid; this is representative, not parcel-wide sampling."""
        latitude, longitude = self.polygon_centroid(geojson_polygon)
        return {
            "latitude": latitude,
            "longitude": longitude,
            "elevation_m": self.get_elevation(latitude, longitude),
            "basis": "Representative elevation sampled at the user-defined polygon centroid; not parcel-wide terrain sampling.",
        }

    def estimate_terrain_relative_elevation(
        self,
        lat: float,
        lon: float,
        regional_baseline_elevation_m: float | None = None,
    ) -> dict[str, Any]:
        """Return where the parcel sits relative to the surrounding terrain.

        THIS IS NOT A FLOOD ASSESSMENT. It compares one elevation point with the
        land around it. It uses no rainfall, drainage, watercourse, river-stage,
        coastal or flood-hazard-map data, and therefore cannot distinguish
        coastal, fluvial and pluvial flooding, nor establish that an inland
        parcel is safe. It is exposed as a labelled terrain indicator only.

        When no baseline is supplied, one is derived from the land around the
        parcel. An explicit ``regional_baseline_elevation_m`` still wins, so a
        deployment with a real regional datum can pass it in.
        """
        ElevationClient._validate_coordinate(lat, lon)
        terrain = self.sample_terrain(lat, lon)
        elevation = terrain["elevation_m"]
        if regional_baseline_elevation_m is not None and math.isfinite(float(regional_baseline_elevation_m)):
            baseline = float(regional_baseline_elevation_m)
            source = "the configured regional baseline"
        else:
            baseline = float(terrain["baseline_m"])
            source = (
                f"the median of {terrain['sample_count']} surrounding samples "
                f"within {terrain['radius_km']:.0f} km"
            )

        metres_below_baseline = baseline - float(elevation)
        relief = max(1.0, float(terrain["max_m"]) - float(terrain["min_m"]))
        # Scale by local relief: 5 m below baseline means far more on a flood
        # plain than in hill country, so flat terrain moves the score faster.
        sensitivity = max(1.0, min(8.0, 60.0 / relief))
        relative_component = sensitivity * metres_below_baseline
        # Relative height alone misreads a coast: sampling the sea drags the
        # baseline to 0 m and a deltaic parcel then looks elevated. Low absolute
        # elevation is itself a flood signal, so lowland carries its own term.
        lowland_component = max(0.0, min(1.0, (LOWLAND_ELEVATION_M - float(elevation)) / LOWLAND_ELEVATION_M)) * LOWLAND_MAX_POINTS
        score = int(round(max(0.0, min(100.0, 50.0 + relative_component + lowland_component))))
        relation = "below" if metres_below_baseline >= 0 else "above"
        basis = (
            f"Parcel elevation {float(elevation):.1f} m, {abs(metres_below_baseline):.1f} m {relation} "
            f"{source} ({baseline:.1f} m); local relief {relief:.0f} m"
            + (f"; lowland adjustment +{lowland_component:.0f}" if lowland_component >= 0.5 else "")
            + f". This {score}/100 figure is a RELATIVE TERRAIN POSITION indicator only. "
            "It is not a flood probability: it uses no rainfall, drainage, watercourse, "
            "river-stage or coastal data, and no flood hazard map. Do not read it as flood risk."
        )
        return {
            "score": score,
            "basis": basis,
            "elevation_m": float(elevation),
            "baseline_m": baseline,
            "relief_m": relief,
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
    client = ElevationClient()
    representative = client.get_polygon_representative_elevation(pune_sample_polygon)
    flood_proxy = client.estimate_terrain_relative_elevation(
        representative["latitude"],
        representative["longitude"],
        regional_baseline_elevation_m=560.0,
    )
    print(json.dumps({"representative_elevation": representative, "flood_risk_proxy": flood_proxy}, indent=2))
