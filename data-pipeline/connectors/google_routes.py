"""Optional Google Routes API adapter; straight-line OSM remains the default."""

from __future__ import annotations

import os
from typing import Any

import requests


class GoogleRoutesClient:
    endpoint = "https://routes.googleapis.com/directions/v2:computeRoutes"

    def __init__(self, api_key: str | None = None):
        self.api_key = (api_key or os.getenv("GOOGLE_ROUTES_API_KEY") or os.getenv("GOOGLE_MAPS_API_KEY") or "").strip()

    @property
    def enabled(self) -> bool:
        return bool(self.api_key) and os.getenv("GOOGLE_ROUTES_ENABLED", "false").casefold() == "true"

    def route(self, origin: tuple[float, float], destination: tuple[float, float]) -> dict[str, Any] | None:
        if not self.enabled:
            return None
        payload = {"origin": {"location": {"latLng": {"latitude": origin[1], "longitude": origin[0]}}},
                   "destination": {"location": {"latLng": {"latitude": destination[1], "longitude": destination[0]}}},
                   "travelMode": "DRIVE", "routingPreference": "TRAFFIC_UNAWARE", "computeAlternativeRoutes": False, "units": "METRIC"}
        try:
            response = requests.post(self.endpoint, headers={"Content-Type": "application/json", "X-Goog-Api-Key": self.api_key,
                "X-Goog-FieldMask": "routes.distanceMeters,routes.duration"}, json=payload, timeout=8)
            response.raise_for_status()
            route = (response.json().get("routes") or [None])[0]
            if not route or not isinstance(route.get("distanceMeters"), (int, float)):
                return None
            duration = str(route.get("duration") or "").removesuffix("s")
            return {"distance_m": round(float(route["distanceMeters"]), 1), "duration_s": float(duration) if duration.replace('.', '', 1).isdigit() else None}
        except (requests.RequestException, TypeError, ValueError, KeyError):
            return None
