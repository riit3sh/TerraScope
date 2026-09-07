"""Internal blocking API for initial TerraScope evidence collection."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from db.repository import SnapshotAlreadyExistsError, get_analysis_snapshot, init_db, save_analysis_snapshot
from etl_pipeline import EvidenceSnapshotValidationError, build_evidence_snapshot


LOGGER = logging.getLogger(__name__)
app = FastAPI(title="TerraScope Internal Evidence API")


class AnalysisBuildRequest(BaseModel):
    polygon: dict[str, Any]
    date_from: str
    date_to: str
    address: str | None = Field(default=None, min_length=1)


@app.on_event("startup")
def startup() -> None:
    init_db()


@app.get("/health")
def health() -> dict[str, str]:
    return {"service": "data-pipeline", "status": "ok"}


@app.post("/internal/analysis/build")
def build_analysis(request: AnalysisBuildRequest) -> dict[str, Any]:
    """Collect and persist one blocking, immutable evidence snapshot."""
    try:
        snapshot = build_evidence_snapshot(
            request.polygon,
            request.date_from,
            request.date_to,
            request.address,
        )
        return save_analysis_snapshot(snapshot)
    except (ValueError, EvidenceSnapshotValidationError) as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    except SnapshotAlreadyExistsError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    except Exception as error:
        LOGGER.exception("Evidence collection failed")
        raise HTTPException(status_code=502, detail=f"Evidence collection failed: {error}") from error


@app.get("/internal/analysis/{snapshot_id}")
def read_analysis(snapshot_id: str) -> dict[str, Any]:
    snapshot = get_analysis_snapshot(snapshot_id)
    if snapshot is None:
        raise HTTPException(status_code=404, detail=f"Analysis snapshot not found: {snapshot_id}")
    return snapshot

