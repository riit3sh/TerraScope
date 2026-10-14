"""Select TerraScope's configured satellite evidence provider."""

from __future__ import annotations

import logging
import os
from typing import Any


LOGGER = logging.getLogger(__name__)


# .env.example ships these as placeholders; treating them as real credentials
# sent every analysis down the AppEEARS path, which then failed and fell back to
# invented data. A placeholder is not configuration.
_PLACEHOLDER_MARKERS = ("your_", "changeme", "placeholder", "xxx", "<", "demo-")


def _is_real(value: str | None) -> bool:
    if not value or not value.strip():
        return False
    lowered = value.strip().lower()
    return not any(marker in lowered for marker in _PLACEHOLDER_MARKERS)


def _appeears_configured() -> bool:
    return bool(
        _is_real(os.getenv("NASA_APPEEARS_TOKEN"))
        or (_is_real(os.getenv("NASA_APPEEARS_USERNAME")) and _is_real(os.getenv("NASA_APPEEARS_PASSWORD")))
    )


def get_satellite_client() -> Any:
    """Return the configured provider.

    Default is Planetary Computer: it serves real Sentinel-2 L2A with no
    credentials, so the stock configuration retrieves genuine imagery instead of
    falling back to invented numbers. AppEEARS is used when its credentials are
    present, or when explicitly selected.
    """
    provider = os.getenv("SATELLITE_PROVIDER", "").strip().lower()
    if not provider:
        provider = "appeears" if _appeears_configured() else "planetary"

    if provider in {"planetary", "planetary_computer", "sentinel2", "pc"}:
        from connectors.satellite_planetary import PlanetaryComputerClient

        return PlanetaryComputerClient()
    if provider in {"appeears", "nasa", "nasa_appeears"}:
        if not _appeears_configured():
            LOGGER.warning(
                "SATELLITE_PROVIDER=appeears but no Earthdata credentials are set; "
                "real imagery will be unavailable."
            )
        from connectors.satellite_appeears import AppEEARSClient

        return AppEEARSClient()
    if provider in {"cdse", "sentinelhub", "copernicus"}:
        from connectors.satellite_sentinelhub import SentinelHubClient

        return SentinelHubClient()
    raise ValueError(f"Unsupported SATELLITE_PROVIDER={provider!r}; use planetary, appeears or cdse.")
