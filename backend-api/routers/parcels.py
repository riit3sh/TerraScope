"""Parcel analysis orchestration routes."""

from __future__ import annotations

import asyncio
import io
import logging
import os
import time
from datetime import date
from typing import Any, Literal

import httpx
from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, ConfigDict, Field

from . import places
from .store import (
    PAGE_BREAK,
    get_document_texts,
    get_land_details,
    get_latest_evaluation,
    get_latest_for_parcel,
    get_snapshot,
    init_store,
    list_documents,
    list_saved_reports,
    save_document,
    save_evaluation,
    save_land_details,
    save_snapshot,
)

from routers.legal_checks import latest_checks

LOGGER = logging.getLogger(__name__)
router = APIRouter()
init_store()
_geocode_cache: dict[str, list[dict[str, Any]]] = {}
_geocode_lock = asyncio.Lock()
_last_geocode_request_at = 0.0


class AnalyzeRequest(BaseModel):
    polygon: dict[str, Any]
    address: str | None = None
    analysis_date_from: date
    analysis_date_to: date


class Preferences(BaseModel):
    """Every preference here changes the evaluation; anything else is rejected rather than ignored."""

    model_config = ConfigDict(extra="forbid")
    road_importance: Literal["low", "medium", "high"] = "medium"
    school_importance: Literal["low", "medium", "high"] = "medium"
    # Distance at which the road / school sub-score reaches 0. The collector searches 5 km,
    # so a feature beyond it is "not found"; it scores 0 only when the limit is within 5 km.
    max_road_distance_m: float = Field(3000, ge=100, le=20000)
    max_school_distance_m: float = Field(5000, ge=100, le=20000)
    rera_requirement: Literal["strict", "important", "informational"] = "informational"


class EvaluationRequest(BaseModel):
    analysis_snapshot_id: str
    profile: str
    property_type: str
    investment_horizon: str
    weights: dict[str, float]
    preferences: Preferences = Field(default_factory=Preferences)


IDENTIFIER = r"^[\w .,/()'-]{1,80}$"
DOC_TYPES = ("patta_chitta", "encumbrance_certificate", "sale_deed", "layout_or_building_approval", "fmb_sketch", "other")


class LandDetails(BaseModel):
    """Survey identifiers as the user states them. Stored as claims; never treated as a matched land record."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    state: str | None = Field(None, pattern=IDENTIFIER)
    district: str | None = Field(None, pattern=IDENTIFIER)
    taluk: str | None = Field(None, pattern=IDENTIFIER)
    village: str | None = Field(None, pattern=IDENTIFIER)
    survey_number: str | None = Field(None, pattern=r"^[0-9A-Za-z/ .-]{1,30}$")
    subdivision: str | None = Field(None, pattern=r"^[0-9A-Za-z/ .-]{1,30}$")


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


def _timeout_seconds(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except ValueError:
        LOGGER.warning("Invalid %s; falling back to %ss", name, default)
        return default


def _service_url(name: str, default: str) -> str:
    return (os.getenv(name) or default).rstrip("/")


# Loopback defaults serve a bare local run. Compose sets both variables to its
# service DNS names (data-pipeline, ml-models), which do not resolve outside the
# Docker network and fail on Windows with "[Errno 11001] getaddrinfo failed".
def data_pipeline_url() -> str:
    return _service_url("DATA_PIPELINE_URL", "http://127.0.0.1:8001")


def ml_models_url() -> str:
    return _service_url("ML_MODELS_URL", "http://127.0.0.1:8002")


def _connection_error(action: str, error: httpx.HTTPError) -> HTTPException:
    """Name the service and address that failed, not just the socket error."""
    try:
        url = str(error.request.url)
    except RuntimeError:  # no request attached
        return HTTPException(status_code=502, detail=f"{action} failed: {error}")
    service = "data-pipeline" if url.startswith(data_pipeline_url()) else "ml-models"
    origin = "/".join(url.split("/", 3)[:3])
    reason = f" ({error})" if str(error) else ""
    return HTTPException(
        status_code=502,
        detail=f"{action} failed: could not reach {service} at {origin}{reason}. It may not be running: "
               "restart TerraScope with terrascope.cmd start, or see its log in .local-ui-check\\logs.",
    )


def _downstream_error(response: httpx.Response, service: str) -> HTTPException:
    """Relay a downstream failure with its own status and message."""
    try:
        detail = response.json().get("detail")
    except ValueError:
        detail = None
    detail = detail or response.text or f"HTTP {response.status_code}"
    # Client errors (bad polygon, missing data) keep their status; server failures become 502.
    status = response.status_code if 400 <= response.status_code < 500 or response.status_code == 503 else 502
    return HTTPException(status_code=status, detail=f"{service}: {detail}")


@router.get("/api/v1/search/suggest")
def suggest_places(q: str, limit: int = 8) -> list[dict[str, Any]]:
    """Autocomplete from the local GeoNames index. Never calls a web service."""
    try:
        return places.suggest(q, max(1, min(limit, 20)))
    except places.PlaceIndexMissing as error:
        raise HTTPException(status_code=503, detail=str(error)) from error


@router.get("/api/v1/search/geocode")
async def geocode_search(q: str) -> list[dict[str, Any]]:
    """Explicit search (the user pressed Search): the local index first, then one
    Nominatim lookup for full addresses. Never used for autocomplete, which the
    Nominatim usage policy forbids; rate-limited to one request per second and cached."""
    global _last_geocode_request_at
    query = q.strip()
    if len(query) < 2:
        return []
    try:
        local = places.suggest(query, 5)
    except places.PlaceIndexMissing:
        local = []
    if local:
        return local
    cache_key = query.casefold()
    if cache_key in _geocode_cache:
        return _geocode_cache[cache_key]
    user_agent = os.getenv("NOMINATIM_USER_AGENT", "terrascope-local-demo/1.0")
    async with _geocode_lock:
        if cache_key in _geocode_cache:
            return _geocode_cache[cache_key]
        delay = 1.0 - (time.monotonic() - _last_geocode_request_at)
        if delay > 0:
            await asyncio.sleep(delay)
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    "https://nominatim.openstreetmap.org/search",
                    params={"q": query, "format": "jsonv2", "addressdetails": 1, "countrycodes": "in", "limit": 5},
                    headers={"Accept": "application/json", "User-Agent": user_agent},
                    timeout=httpx.Timeout(connect=3.0, read=10.0, write=5.0, pool=3.0),
                )
                _last_geocode_request_at = time.monotonic()
                response.raise_for_status()
                results = response.json()
        except httpx.TimeoutException as error:
            raise HTTPException(status_code=504, detail="Address search timed out. Try a more specific place.") from error
        except httpx.HTTPError as error:
            raise HTTPException(status_code=502, detail=f"Address search failed: {error}") from error
    suggestions = [
        {"lat": float(item["lat"]), "lon": float(item["lon"]), "display_name": item["display_name"],
         "kind": item.get("type"), "precision": "address match", "source": "OpenStreetMap Nominatim"}
        for item in results
    ]
    _geocode_cache[cache_key] = suggestions
    return suggestions


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
                f"{data_pipeline_url()}/internal/analysis/build",
                json=payload,
                timeout=evidence_timeout,
            )
            if not evidence_response.is_success:
                raise _downstream_error(evidence_response, "data-pipeline")
            evidence_snapshot = evidence_response.json()
            if evidence_snapshot.get("status") == "outside_coverage":
                # Nothing was collected, so there is nothing to enrich, score or save.
                return {"status": "outside_coverage", "coverage": evidence_snapshot.get("coverage")}
            enrich_response = await client.post(
                f"{ml_models_url()}/internal/ml/enrich",
                json={"snapshot": evidence_snapshot},
                timeout=ml_timeout,
            )
            if not enrich_response.is_success:
                raise _downstream_error(enrich_response, "ml-models enrichment")
            enriched_snapshot = enrich_response.json()
    except httpx.ConnectTimeout as error:
        raise _connection_error("Initial evidence collection", error) from error
    except httpx.TimeoutException as error:
        raise HTTPException(status_code=504, detail=f"Initial evidence collection timed out: {error}") from error
    except httpx.HTTPError as error:
        raise _connection_error("Initial evidence collection", error) from error
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
        "preferences": request.preferences.model_dump(),
    }
    uploaded_documents = get_document_texts(parcel_id)
    request_snapshot = dict(snapshot)
    if uploaded_documents:
        request_snapshot["uploaded_documents"] = uploaded_documents
    supplied, documents = get_land_details(parcel_id), list_documents(parcel_id)
    if supplied or documents:
        request_snapshot["user_land_details"] = {
            **(supplied or {}),
            "documents": [{key: doc[key] for key in ("filename", "doc_type", "text_extracted", "pages")} for doc in documents],
        }
    recorded = latest_checks(parcel_id)
    if recorded:  # the buyer's statements; the verdict treats them as such, never as verification
        request_snapshot["user_legal_checks"] = recorded
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{ml_models_url()}/internal/ml/evaluate",
                json={"snapshot": request_snapshot, "evaluation": evaluation},
                timeout=httpx.Timeout(
                    connect=2.0,
                    # Must exceed ml-models' own retrieval + Groq budget, or the
                    # optional AI step is cut off before it can degrade gracefully.
                    read=_timeout_seconds("EVALUATE_READ_TIMEOUT_SECONDS", 90.0),
                    write=10.0,
                    pool=5.0,
                ),
            )
            if not response.is_success:
                raise _downstream_error(response, "ml-models evaluation")
            result = response.json()
    except httpx.ConnectTimeout as error:
        # Windows reports a refused loopback connection as a connect timeout: the service is not running.
        raise _connection_error("Evaluation", error) from error
    except httpx.TimeoutException as error:
        raise HTTPException(status_code=504, detail=f"Evaluation timed out: {error}") from error
    except httpx.HTTPError as error:
        raise _connection_error("Evaluation", error) from error
    save_evaluation(parcel_id, request.analysis_snapshot_id, result)
    return result


def _document_text(content: bytes, extension: str, content_type: str) -> str | None:
    """Extract indexable text from an uploaded evidence file, or None if there is none."""
    if extension == "txt" or content_type == "text/plain":
        return content.decode("utf-8", errors="replace").strip() or None
    try:
        from pypdf import PdfReader

        pages = PdfReader(io.BytesIO(content)).pages
        # Pages stay separable, so a citation can name the page an identifier was found on.
        text = PAGE_BREAK.join(page.extract_text() or "" for page in pages)
        return text if text.replace(PAGE_BREAK, "").strip() else None
    except Exception as error:  # scanned or malformed PDFs stay stored but unindexed
        LOGGER.warning("Could not extract text from uploaded evidence: %s", error)
        return None


@router.post("/api/v1/parcels/{parcel_id}/documents")
async def upload_parcel_document(parcel_id: str, file: UploadFile = File(...),
                                 doc_type: str | None = Form(None)) -> dict[str, Any]:
    if doc_type is not None and doc_type not in DOC_TYPES:
        raise HTTPException(status_code=400, detail=f"doc_type must be one of {', '.join(DOC_TYPES)}.")
    content_type = file.content_type or "application/octet-stream"
    filename = file.filename or "upload"
    extension = filename.lower().rsplit(".", 1)[-1] if "." in filename else ""
    if extension not in {"pdf", "txt"} and content_type not in {"application/pdf", "text/plain"}:
        raise HTTPException(status_code=400, detail="Only PDF and TXT evidence files are accepted.")
    if get_latest_for_parcel(parcel_id) is None:
        raise HTTPException(status_code=404, detail=f"Parcel not found: {parcel_id}")
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="The file is empty.")
    if len(content) > 10 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Evidence files must be 10 MB or smaller.")
    text_content = _document_text(content, extension, content_type)
    document_id = save_document(parcel_id, filename, content_type, len(content), text_content, doc_type)
    return {"document_id": document_id, "parcel_id": parcel_id, "filename": filename, "doc_type": doc_type,
            "text_indexed": text_content is not None,
            "pages": text_content.count(PAGE_BREAK) + 1 if text_content and PAGE_BREAK in text_content else None}


@router.get("/api/v1/parcels/{parcel_id}/land-details")
def read_land_details(parcel_id: str) -> dict[str, Any]:
    return {"parcel_id": parcel_id, "details": get_land_details(parcel_id), "documents": list_documents(parcel_id),
            "verification_status": "user_provided_unverified"}


@router.put("/api/v1/parcels/{parcel_id}/land-details")
def write_land_details(parcel_id: str, details: LandDetails) -> dict[str, Any]:
    """Store the user's survey identifiers. Re-evaluate to see them in the report; they never verify title."""
    if get_latest_for_parcel(parcel_id) is None:
        raise HTTPException(status_code=404, detail=f"Parcel not found: {parcel_id}")
    save_land_details(parcel_id, details.model_dump(exclude_none=True))
    return read_land_details(parcel_id)


@router.get("/api/v1/parcels")
def list_parcels(limit: int = 1000) -> dict[str, Any]:
    """Saved reports, newest first, so a user can reopen earlier work."""
    return {"reports": list_saved_reports(max(1, min(limit, 5000)))}


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
        "documents": list_documents(parcel_id),
        "land_details": get_land_details(parcel_id),
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
