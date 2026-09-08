"""Select TerraScope's configured satellite evidence provider."""

from __future__ import annotations

import os
from typing import Any


def get_satellite_client() -> Any:
    provider = os.getenv("SATELLITE_PROVIDER", "appeears").strip().lower()
    if provider in {"appeears", "nasa", "nasa_appeears"}:
        from connectors.satellite_appeears import AppEEARSClient

        return AppEEARSClient()
    if provider in {"cdse", "sentinelhub", "copernicus"}:
        from connectors.satellite_sentinelhub import SentinelHubClient

        return SentinelHubClient()
    raise ValueError(f"Unsupported SATELLITE_PROVIDER={provider!r}; use appeears or cdse.")

