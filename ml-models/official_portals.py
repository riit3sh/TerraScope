"""Official portals for a parcel's state: where a buyer checks title and RERA. A link is never verification.

Data: docs/datasets/official_portals.json (MoHUA's RERA authority list; land-record portals only where checked).
"""

from __future__ import annotations

import json
import unicodedata
from functools import lru_cache
from pathlib import Path
from typing import Any


@lru_cache(maxsize=1)
def _regions() -> dict[str, dict[str, Any]]:
    for root in (Path(__file__).resolve().parent, Path(__file__).resolve().parents[1]):
        path = root / "docs" / "datasets" / "official_portals.json"
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))["regions"]
    return {}  # file missing: every portal reads as unknown, never as "none exists"


def _fold(name: str | None) -> str:
    return unicodedata.normalize("NFKD", name or "").encode("ascii", "ignore").decode().casefold().strip()


def for_state(state: str | None) -> dict[str, Any] | None:
    """The region's entry by name (accents and case ignored), or None when the state is unknown."""
    wanted = _fold(state)
    return next((entry for entry in _regions().values() if _fold(entry["name"]) == wanted), None) if wanted else None
