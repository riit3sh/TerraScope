"""SQLAlchemy model for the immutable TerraScope evidence snapshot."""

from __future__ import annotations

from datetime import datetime

from geoalchemy2 import Geometry
from sqlalchemy import DateTime, JSON, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class AnalysisSnapshot(Base):
    """One immutable evidence collection for one parcel and date interval."""

    __tablename__ = "analysis_snapshots"

    snapshot_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    parcel_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    geometry: Mapped[object] = mapped_column(
        Geometry(geometry_type="POLYGON", srid=4326, spatial_index=False), nullable=False
    )
    location: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    geometry_metadata: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    land_records: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    rera: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    satellite: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    infrastructure: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    risk: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    evidence: Mapped[list | None] = mapped_column(JSON, nullable=True)
    snapshot_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

