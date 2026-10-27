"""Small optional Google Places (New) adapter for nearby facilities."""

from __future__ import annotations

import math
import os
from typing import Any

import requests


def _haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in metres (straight line, like the OSM distances)."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    a = math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(math.radians(lon2 - lon1) / 2) ** 2
    return 2 * 6_371_008.8 * math.asin(math.sqrt(a))


class GooglePlacesClient:
    endpoint = "https://places.googleapis.com/v1/places:searchNearby"

    def __init__(self, api_key: str | None = None):
        self.api_key = (api_key or os.getenv("GOOGLE_PLACES_API_KEY") or os.getenv("GOOGLE_MAPS_API_KEY") or "").strip()

    @property
    def enabled(self) -> bool:
        return bool(self.api_key) and os.getenv("GOOGLE_PLACES_ENABLED", "true").casefold() == "true"

    def nearby(self, lat: float, lon: float, place_type: str, radius_m: float = 5000) -> list[dict[str, Any]]:
        if not self.enabled:
            return []
        payload = {"includedTypes": [place_type], "maxResultCount": 20,
                   "rankPreference": "DISTANCE",
                   "locationRestriction": {"circle": {"center": {"latitude": lat, "longitude": lon}, "radius": radius_m}}}
        try:
            response = requests.post(self.endpoint, headers={"Content-Type": "application/json", "X-Goog-Api-Key": self.api_key,
                "X-Goog-FieldMask": "places.id,places.displayName,places.location,places.primaryType"}, json=payload, timeout=8)
            response.raise_for_status()
            result = []
            for item in response.json().get("places", []):
                location = item.get("location") or {}
                if isinstance(location.get("latitude"), (int, float)) and isinstance(location.get("longitude"), (int, float)):
                    # Same shape as a LocalOSM hit (distance_m included), so callers can use either source.
                    result.append({"lat": location["latitude"], "lon": location["longitude"],
                                   "distance_m": round(_haversine_m(lat, lon, location["latitude"], location["longitude"]), 2),
                                   "name": (item.get("displayName") or {}).get("text"),
                                   "class": item.get("primaryType") or place_type, "tags": {"source": "Google Places API"},
                                   "place_id": item.get("id")})
            return sorted(result, key=lambda hit: hit["distance_m"])
        except (requests.RequestException, TypeError, ValueError, KeyError):
            return []
