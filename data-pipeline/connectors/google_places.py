"""Small optional Google Places (New) adapter for nearby facilities."""

from __future__ import annotations

import os
from typing import Any

import requests


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
                    result.append({"lat": location["latitude"], "lon": location["longitude"],
                                   "name": (item.get("displayName") or {}).get("text"),
                                   "class": item.get("primaryType") or place_type, "tags": {"source": "Google Places API"},
                                   "place_id": item.get("id")})
            return result
        except (requests.RequestException, TypeError, ValueError, KeyError):
            return []
