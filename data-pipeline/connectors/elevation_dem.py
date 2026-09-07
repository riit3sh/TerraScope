"""Open-Elevation connector and coarse elevation-relative flood proxy."""

from __future__ import annotations

import json
import logging
import math
import time
from typing import Any

import requests


LOGGER = logging.getLogger(__name__)


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

    def estimate_flood_risk_proxy(
        self,
        lat: float,
        lon: float,
        regional_baseline_elevation_m: float,
    ) -> dict[str, Any]:
        """Return a coarse elevation-relative flood-risk proxy.

        This is not a hydrological model. It only compares one representative
        point's elevation with a regional baseline; a real deployment should
        use CWC flood atlas data and additional hydrological inputs.

        The point lookup is performed through this client's session.
        """
        ElevationClient._validate_coordinate(lat, lon)
        if not math.isfinite(float(regional_baseline_elevation_m)):
            raise ValueError("regional_baseline_elevation_m must be finite.")
        elevation = self.get_elevation(lat, lon)
        if not math.isfinite(float(elevation)):
            raise ValueError("point elevation must be finite.")

        metres_below_baseline = float(regional_baseline_elevation_m) - float(elevation)
        # Baseline equals 50. Every metre below adds two points; clamp to 0-100.
        score = int(round(max(0.0, min(100.0, 50.0 + 2.0 * metres_below_baseline))))
        relation = "below" if metres_below_baseline >= 0 else "above"
        basis = (
            f"Representative point elevation is {float(elevation):.1f} m, "
            f"{abs(metres_below_baseline):.1f} m {relation} the regional baseline of "
            f"{float(regional_baseline_elevation_m):.1f} m. The resulting {score}/100 score "
            "is a coarse elevation-relative proxy, not a hydrological model; real deployment should use CWC flood atlas data."
        )
        return {"score": score, "basis": basis}


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
    flood_proxy = client.estimate_flood_risk_proxy(
        representative["latitude"],
        representative["longitude"],
        regional_baseline_elevation_m=560.0,
    )
    print(json.dumps({"representative_elevation": representative, "flood_risk_proxy": flood_proxy}, indent=2))
