"""Parcel analysis orchestration routes."""

from __future__ import annotations

import json
import os
from datetime import date
from typing import Any

import httpx
from fastapi import APIRouter, File, HTTPException, UploadFile
from pydantic import BaseModel, Field

from .store import (
    get_document_texts,
    get_latest_evaluation,
    get_latest_for_parcel,
    get_snapshot,
    init_store,
    save_document,
    save_evaluation,
    save_snapshot,
)


router = APIRouter()
init_store()
_geocode_cache: dict[str, dict[str, Any] | None] = {}


class AnalyzeRequest(BaseModel):
    polygon: dict[str, Any]
    address: str | None = None
    analysis_date_from: date
    analysis_date_to: date


class EvaluationRequest(BaseModel):
    analysis_snapshot_id: str
    profile: str
    property_type: str
    investment_horizon: str
    weights: dict[str, float]
    preferences: dict[str, Any]


def _validate_polygon(polygon: dict[str, Any]) -> None:
    if polygon.get("type") != "Polygon":
        raise HTTPException(status_code=400, detail="polygon must be a GeoJSON Polygon geometry.")
    coordinates = polygon.get("coordinates")
    if not isinstance(coordinates, list) or not coordinates or not isinstance(coordinates[0], list):
        raise HTTPException(status_code=400, detail="polygon must contain an exterior linear ring.")
    for ring in coordinates:
        if not isinstance(ring, list) or len(ring) < 4 or ring[0] != ring[-1]:
            raise HTTPException(status_code=400, detail="Polygon rings must contain at least four positions and be closed.")
        for position in ring:
            if not isinstance(position, list) or len(position) < 2:
                raise HTTPException(status_code=400, detail="Polygon positions must be [longitude, latitude] pairs.")
            if not all(isinstance(value, (int, float)) for value in position[:2]):
                raise HTTPException(status_code=400, detail="Polygon coordinates must be numeric.")


def _service_url(name: str, default: str) -> str:
    return os.getenv(name, default).rstrip("/")


def _downstream_error(response: httpx.Response, service: str) -> HTTPException:
    return HTTPException(status_code=502, detail=f"{service} returned HTTP {response.status_code}: {response.text[:500]}")


@router.get("/api/v1/search/geocode")
async def geocode_search(q: str) -> dict[str, Any] | None:
    """Explicit search-only Nominatim proxy with a small process-local cache."""
    query = q.strip()
    if not query:
        raise HTTPException(status_code=400, detail="Search text is required.")
    cache_key = query.casefold()
    if cache_key in _geocode_cache:
        return _geocode_cache[cache_key]
    user_agent = os.getenv("NOMINATIM_USER_AGENT", "terrascope-local-demo/1.0")
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                "https://nominatim.openstreetmap.org/search",
                params={"q": query, "format": "json", "limit": 1},
                headers={"Accept": "application/json", "User-Agent": user_agent},
                timeout=httpx.Timeout(connect=3.0, read=10.0, write=5.0, pool=3.0),
            )
            response.raise_for_status()
            results = response.json()
    except httpx.TimeoutException as error:
        raise HTTPException(status_code=504, detail="Address search timed out. Try a more specific place.") from error
    except httpx.HTTPError as error:
        raise HTTPException(status_code=502, detail=f"Address search failed: {error}") from error
    result = None
    if results:
        item = results[0]
        result = {"lat": float(item["lat"]), "lon": float(item["lon"]), "display_name": item["display_name"]}
    _geocode_cache[cache_key] = result
    return result


@router.post("/api/v1/parcels/analyze")
async def analyze_parcel(request: AnalyzeRequest) -> dict[str, Any]:
    _validate_polygon(request.polygon)
    if request.analysis_date_from > request.analysis_date_to:
        raise HTTPException(status_code=400, detail="analysis_date_from must be on or before analysis_date_to.")
    payload = {
        "polygon": request.polygon,
        "address": request.address,
        "date_from": request.analysis_date_from.isoformat(),
        "date_to": request.analysis_date_to.isoformat(),
    }
    evidence_timeout = httpx.Timeout(connect=5.0, read=180.0, write=15.0, pool=10.0)
    ml_timeout = httpx.Timeout(connect=2.0, read=15.0, write=10.0, pool=5.0)
    try:
        async with httpx.AsyncClient() as client:
            evidence_response = await client.post(
                f"{_service_url('DATA_PIPELINE_URL', 'http://data-pipeline:8001')}/internal/analysis/build",
                json=payload,
                timeout=evidence_timeout,
            )
            if not evidence_response.is_success:
                raise _downstream_error(evidence_response, "data-pipeline")
            evidence_snapshot = evidence_response.json()
            enrich_response = await client.post(
                f"{_service_url('ML_MODELS_URL', 'http://ml-models:8002')}/internal/ml/enrich",
                json={"snapshot": evidence_snapshot},
                timeout=ml_timeout,
            )
            if not enrich_response.is_success:
                raise _downstream_error(enrich_response, "ml-models enrichment")
            enriched_snapshot = enrich_response.json()
    except httpx.TimeoutException as error:
        raise HTTPException(status_code=504, detail=f"Initial evidence collection timed out: {error}") from error
    except httpx.HTTPError as error:
        raise HTTPException(status_code=502, detail=f"Initial evidence collection failed: {error}") from error
    save_snapshot(enriched_snapshot)
    return {
        "analysis_snapshot_id": enriched_snapshot["metadata"]["analysis_snapshot_id"],
        "evidence_snapshot": enriched_snapshot,
    }


@router.post("/api/v1/parcels/{parcel_id}/evaluate")
async def evaluate_parcel(parcel_id: str, request: EvaluationRequest) -> dict[str, Any]:
    snapshot = get_snapshot(request.analysis_snapshot_id)
    if snapshot is None or snapshot.get("parcel_id") != parcel_id:
        raise HTTPException(status_code=404, detail="Immutable evidence snapshot not found for this parcel.")
    evaluation = {
        "profile": request.profile,
        "property_type": request.property_type,
        "investment_horizon": request.investment_horizon,
        "weights": request.weights,
        "preferences": request.preferences,
    }
    uploaded_documents = get_document_texts(parcel_id)
    request_snapshot = dict(snapshot)
    if uploaded_documents:
        request_snapshot["uploaded_documents"] = uploaded_documents
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{_service_url('ML_MODELS_URL', 'http://ml-models:8002')}/internal/ml/evaluate",
                json={"snapshot": request_snapshot, "evaluation": evaluation},
                timeout=httpx.Timeout(connect=2.0, read=15.0, write=10.0, pool=5.0),
            )
            if not response.is_success:
                raise _downstream_error(response, "ml-models evaluation")
            result = response.json()
    except httpx.TimeoutException as error:
        raise HTTPException(status_code=504, detail=f"Evaluation timed out: {error}") from error
    except httpx.HTTPError as error:
        raise HTTPException(status_code=502, detail=f"Evaluation failed: {error}") from error
    save_evaluation(parcel_id, request.analysis_snapshot_id, result)
    return result


@router.post("/api/v1/parcels/{parcel_id}/documents")
async def upload_parcel_document(parcel_id: str, file: UploadFile = File(...)) -> dict[str, Any]:
    content_type = file.content_type or "application/octet-stream"
    filename = file.filename or "upload"
    extension = filename.lower().rsplit(".", 1)[-1] if "." in filename else ""
    if extension not in {"pdf", "txt"} and content_type not in {"application/pdf", "text/plain"}:
        raise HTTPException(status_code=400, detail="Only PDF and TXT evidence files are accepted.")
    content = await file.read()
    if len(content) > 10 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Evidence files must be 10 MB or smaller.")
    text_content = content.decode("utf-8", errors="replace") if extension == "txt" or content_type == "text/plain" else None
    document_id = save_document(parcel_id, filename, content_type, len(content), text_content)
    return {"document_id": document_id, "parcel_id": parcel_id, "filename": filename, "text_indexed": text_content is not None}


@router.get("/api/v1/parcels/{parcel_id}")
def get_parcel(parcel_id: str) -> dict[str, Any]:
    latest = get_latest_for_parcel(parcel_id)
    if latest is None:
        raise HTTPException(status_code=404, detail=f"Parcel not found: {parcel_id}")
    snapshot_id, snapshot = latest
    return {
        "parcel_id": parcel_id,
        "analysis_snapshot_id": snapshot_id,
        "evidence_snapshot": snapshot,
        "uploaded_documents": get_document_texts(parcel_id),
        "latest_evaluation": get_latest_evaluation(parcel_id),
    }


@router.get("/api/v1/analysis/{analysis_snapshot_id}")
def get_analysis(analysis_snapshot_id: str) -> dict[str, Any]:
    snapshot = get_snapshot(analysis_snapshot_id)
    if snapshot is None:
        raise HTTPException(status_code=404, detail=f"Analysis snapshot not found: {analysis_snapshot_id}")
    return snapshot


@router.get("/api/v1/health")
def health() -> dict[str, str]:
    return {"service": "backend-api", "status": "ok"}
