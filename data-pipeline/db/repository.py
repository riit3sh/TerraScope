"""Persistence operations for immutable analysis snapshots."""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any

from geoalchemy2.elements import WKTElement
from sqlalchemy import create_engine, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from db.models import AnalysisSnapshot, Base


class SnapshotAlreadyExistsError(RuntimeError):
    """Raised when code attempts to mutate an existing snapshot id."""


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
    with Session(_engine()) as session:
        row = session.scalar(select(AnalysisSnapshot).where(AnalysisSnapshot.snapshot_id == snapshot_id))
        return row.snapshot_json if row else None
