"""Place suggestions from the local GeoNames index (built by `terrascope.cmd fetch-data`).

Typing in the search box must never reach public Nominatim, whose usage policy
forbids autocomplete. This module makes no network calls at all.
"""

from __future__ import annotations

import json
import math
import os
import re
import sqlite3
from pathlib import Path
from typing import Any


class PlaceIndexMissing(RuntimeError):
    pass


def index_dir() -> Path:
    root = os.getenv("TERRASCOPE_DATA_DIR") or str(Path(__file__).resolve().parents[2] / "data-cache")
    return Path(root) / "places"


def index_info() -> dict[str, Any] | None:
    try:
        return json.loads((index_dir() / "manifest.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _tokens(query: str) -> list[str]:
    return re.findall(r"\w+", query.casefold())


def _near(a: dict[str, Any], b: dict[str, Any], km: float = 3.0) -> bool:
    dy = (a["lat"] - b["lat"]) * 111.0
    dx = (a["lon"] - b["lon"]) * 111.0 * math.cos(math.radians(a["lat"]))
    return math.hypot(dx, dy) <= km


def suggest(query: str, limit: int = 8) -> list[dict[str, Any]]:
    """Prefix-match every word against name, alternate names and district/state."""
    tokens = _tokens(query)
    if not tokens or len("".join(tokens)) < 2:
        return []
    path = index_dir() / "places.sqlite"
    if not path.exists():
        raise PlaceIndexMissing(
            "The place-search index is not installed. Run: terrascope.cmd fetch-data"
        )
    match = " ".join(f'"{token}"*' for token in tokens)
    with sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True) as db:
        db.row_factory = sqlite3.Row
        # ponytail: ORDER BY over every FTS hit; a 2-letter prefix matches ~10^5 rows.
        # Measured p95 is in docs/STATUS.md; add a prominent-places table if it grows.
        rows = db.execute(
            """
            SELECT p.* FROM places_fts f JOIN places p ON p.id = f.rowid
            WHERE places_fts MATCH ? ORDER BY p.rank, p.population DESC LIMIT 400
            """,
            (match,),
        ).fetchall()
    phrase = " ".join(tokens)

    def quality(row: sqlite3.Row) -> tuple:
        # Name match and prominence trade off: Chennai found by its alternate name
        # "Madras" outranks a post office whose name merely starts with "madras".
        name = " ".join(_tokens(re.sub(r"\(PIN \d+\)", "", row["name"])))
        exact = name == phrase or name == tokens[0]
        prefix = name.startswith(phrase) or name.startswith(tokens[0])
        return ((0 if exact else 1 if prefix else 2) + row["rank"] / 2, -row["population"], len(name))

    results: list[dict[str, Any]] = []
    for row in sorted(rows, key=quality):
        item = {
            "lat": row["lat"],
            "lon": row["lon"],
            "name": row["name"],
            "kind": row["kind"],
            "district": row["district"] or None,
            "state": row["state"] or None,
            "display_name": ", ".join(part for part in (row["name"], row["district"], row["state"], "India") if part),
            "precision": row["precision"],
            "source": row["source"],
        }
        base = item["name"].split(" (PIN")[0].casefold()
        if any(base == other["name"].split(" (PIN")[0].casefold() and other["state"] == item["state"]
               and _near(item, other) for other in results):
            continue
        results.append(item)
        if len(results) >= limit:
            break
    return results
