"""Persistence operations for immutable analysis snapshots."""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Any

from geoalchemy2.elements import WKTElement
from sqlalchemy import create_engine, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from db.models import AnalysisSnapshot, Base


LOGGER = logging.getLogger(__name__)


class SnapshotAlreadyExistsError(RuntimeError):
    """Raised when code attempts to mutate an existing snapshot id."""


def persistence_enabled() -> bool:
    """Whether the PostGIS snapshot archive is configured.

    Compose always sets DATABASE_URL, so this is True there. Running the service
    directly on Windows for UI work has no PostGIS, and the geometry column needs
    it; rather than refuse to start, the archive is skipped. The backend keeps its
    own copy of every snapshot, so nothing collected is lost -- only the
    second, spatial archive. A DATABASE_URL that is set but unreachable still
    fails loudly, so a real misconfiguration is never masked.
    """
    return bool(os.getenv("DATABASE_URL"))


def _database_url() -> str:
    value = os.getenv("DATABASE_URL")
    if not value:
        raise RuntimeError("DATABASE_URL must be set to use snapshot persistence.")
    if value.startswith("postgresql://"):
        return value.replace("postgresql://", "postgresql+psycopg://", 1)
    return value


def _engine():
    return create_engine(_database_url(), pool_pre_ping=True)


def init_db() -> None:
    """Create the snapshot table; PostGIS itself is initialized by Compose."""
    if not persistence_enabled():
        LOGGER.warning(
            "DATABASE_URL is not set: the PostGIS snapshot archive is disabled. "
            "Evidence is still collected and returned, and the backend still stores it."
        )
        return
    Base.metadata.create_all(_engine())


def _polygon_wkt(geometry: dict[str, Any]) -> WKTElement:
    rings = []
    for ring in geometry["coordinates"]:
        coordinates = ", ".join(f"{position[0]} {position[1]}" for position in ring)
        rings.append(f"({coordinates})")
    return WKTElement(f"POLYGON({', '.join(rings)})", srid=4326)


def save_analysis_snapshot(snapshot: dict[str, Any]) -> dict[str, Any]:
    """Insert and return a snapshot; existing ids are never updated."""
    snapshot_id = snapshot["metadata"]["analysis_snapshot_id"]
    if not persistence_enabled():
        return snapshot
    geometry = snapshot["geometry"]
    row = AnalysisSnapshot(
        snapshot_id=snapshot_id,
        parcel_id=snapshot["parcel_id"],
        geometry=_polygon_wkt(geometry),
        location=snapshot.get("location"),
        geometry_metadata=snapshot.get("geometry_metadata"),
        land_records=snapshot.get("land_records"),
        rera=snapshot.get("rera"),
        satellite=snapshot.get("satellite"),
        infrastructure=snapshot.get("infrastructure"),
        risk=snapshot.get("risk"),
        evidence=snapshot.get("evidence"),
        snapshot_json=snapshot,
        created_at=datetime.now(timezone.utc),
    )
    try:
        with Session(_engine()) as session:
            session.add(row)
            session.commit()
    except IntegrityError as error:
        raise SnapshotAlreadyExistsError(f"Analysis snapshot {snapshot_id} already exists and is immutable.") from error
    return snapshot


def get_analysis_snapshot(snapshot_id: str) -> dict[str, Any] | None:
    """Return the canonical collected JSON for a snapshot id, if present."""
    if not persistence_enabled():
        return None
    with Session(_engine()) as session:
        row = session.scalar(select(AnalysisSnapshot).where(AnalysisSnapshot.snapshot_id == snapshot_id))
        return row.snapshot_json if row else None
