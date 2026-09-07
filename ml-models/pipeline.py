"""Pure ML-stage enrichment and evaluation pipeline for TerraScope."""

from __future__ import annotations

import json
import logging
import os
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from jsonschema import Draft202012Validator, FormatChecker
from pydantic import BaseModel

from change_detection.statistical_change import detect_change_from_series
from scoring_engine.scoring import compute_evaluation


LOGGER = logging.getLogger(__name__)
app = FastAPI(title="TerraScope ML Pipeline")
_RAG_CACHE: dict[tuple[str, str], dict[str, Any]] = {}


def _schema_path() -> Path:
    candidates = [
        Path(__file__).resolve().parent / "docs" / "schema" / "parcel_schema.json",
        Path(__file__).resolve().parents[1] / "docs" / "schema" / "parcel_schema.json",
    ]
    for path in candidates:
        if path.exists():
            return path
    return candidates[0]


def _validate_snapshot(snapshot: dict[str, Any]) -> None:
    schema = json.loads(_schema_path().read_text(encoding="utf-8"))
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    errors = sorted(validator.iter_errors(snapshot), key=lambda error: list(error.path))
    if errors:
        details = "; ".join(
            f"{'.'.join(str(part) for part in error.path) or 'root'}: {error.message}" for error in errors[:5]
        )
        raise ValueError(f"Snapshot failed schema validation: {details}")


def enrich_evidence(snapshot: dict[str, Any]) -> dict[str, Any]:
    """Derive statistical satellite change evidence without external calls."""
    enriched = deepcopy(snapshot)
    satellite = enriched.get("satellite") or {}
    enriched["satellite"] = satellite
    series = []
    for item in satellite.get("ndvi_ndbi_series", satellite.get("change_series", [])) or []:
        if isinstance(item, dict) and {"date", "ndvi", "ndbi"} <= item.keys():
            series.append({key: item[key] for key in ("date", "ndvi", "ndbi")})
    if not series:
        series = [
            {"date": ndvi.get("date"), "ndvi": ndvi.get("value"), "ndbi": ndbi.get("value")}
            for ndvi, ndbi in zip(satellite.get("ndvi_trend", []) or [], satellite.get("ndbi_trend", []) or [])
            if isinstance(ndvi, dict) and isinstance(ndbi, dict)
        ]
    change = detect_change_from_series(series)
    satellite.update(change)
    satellite.pop("ndvi_ndbi_series", None)
    satellite.pop("change_series", None)

    evidence = enriched.setdefault("evidence", []) or []
    evidence = [
        item for item in evidence
        if not (isinstance(item, dict) and item.get("source_reference") == "statistical_change_v1")
    ]
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    evidence.append({
        "evidence_id": f"{enriched.get('metadata', {}).get('analysis_snapshot_id', 'snapshot')}:statistical-change",
        "source_type": "derived",
        "source_reference": "statistical_change_v1",
        "title": "Statistical satellite change detection",
        "observed_at": now,
        "freshness": "derived",
        "summary": (
            f"Linear NDVI/NDBI trend classification: {change['change_type']} "
            f"(detected={change['change_detected']}, confidence={change['change_confidence']:.3f})."
        ),
    })
    enriched["evidence"] = evidence
    _validate_snapshot(enriched)
    return enriched


def _maybe_grounded_reasoning(
    snapshot: dict[str, Any],
    documents_override: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Use local/sample RAG only when parcel documents and an API key are available."""
    parcel_id = snapshot.get("parcel_id")
    if not parcel_id or not os.getenv("GROQ_API_KEY"):
        return []
    documents = documents_override
    if documents is None:
        documents = snapshot.get("rag_documents") or snapshot.get("uploaded_documents")
    if documents is None:
        try:
            from rag_pipeline.sample_documents import SAMPLE_DOCUMENTS
            documents = [document for document in SAMPLE_DOCUMENTS if document.get("parcel_id") == parcel_id]
        except ImportError:
            documents = []
    if not documents:
        return []
    question = snapshot.get("rag_question", "Summarize the parcel's title and RERA evidence.")
    cache_key = (str(snapshot.get("metadata", {}).get("analysis_snapshot_id", parcel_id)), question)
    if cache_key not in _RAG_CACHE:
        try:
            from rag_pipeline.ingest import build_vector_index
            from rag_pipeline.reason import generate_grounded_answer
            build_vector_index(documents)
            _RAG_CACHE[cache_key] = generate_grounded_answer(question, str(parcel_id))
        except Exception as error:
            LOGGER.warning("Grounded RAG reasoning unavailable: %s", error)
            _RAG_CACHE[cache_key] = {"answer_text": "", "citations": []}
    return _RAG_CACHE[cache_key].get("citations", [])


def _section(record: dict[str, Any], name: str) -> dict[str, Any]:
    value = record.get(name)
    return value if isinstance(value, dict) else {}


def evaluate_snapshot(snapshot: dict[str, Any], evaluation: dict[str, Any]) -> dict[str, Any]:
    """Evaluate an immutable evidence snapshot without collection connectors."""
    evaluated = deepcopy(snapshot)
    # These are request-scoped RAG inputs, never persisted evidence-schema fields.
    rag_documents = evaluated.pop("rag_documents", None)
    uploaded_documents = evaluated.pop("uploaded_documents", None)
    evaluated["evaluation"] = deepcopy(evaluation)
    result = compute_evaluation(evaluated, evaluation)
    risk = evaluated.setdefault("risk", {}) or {}
    risk["legal_risk_score"] = round(100.0 - result["legal_safety_score"], 2)
    risk.setdefault("flood_risk_score", round(100.0 - result["flood_safety_score"], 2))
    evaluated["risk"] = risk
    opportunity = evaluated.setdefault("opportunity", {}) or {}
    opportunity["growth_score"] = result["growth_score"]
    evaluated["opportunity"] = opportunity
    evaluated["score_breakdown"] = {
        key: result[key]
        for key in (
            "legal_safety_score",
            "accessibility_score",
            "flood_safety_score",
            "growth_score",
            "composite_score",
            "weighted_contributions",
        )
    }
    citations = list(_section(evaluated, "verdict").get("citations", []) or [])
    citations.extend(
        {
            "claim": citation["claim"],
            "source_type": "rag",
            "source_reference": citation["source_reference"],
        }
        for citation in _maybe_grounded_reasoning(
            evaluated,
            rag_documents if rag_documents is not None else uploaded_documents,
        )
    )
    evaluated["verdict"] = {
        "recommendation": result["recommendation"],
        "confidence": result["confidence"],
        "reasoning_summary": result["reasoning_summary"],
        "citations": citations,
    }
    _validate_snapshot(evaluated)
    return evaluated


class EnrichRequest(BaseModel):
    snapshot: dict[str, Any]


class EvaluateRequest(BaseModel):
    snapshot: dict[str, Any]
    evaluation: dict[str, Any]


@app.get("/health")
def health() -> dict[str, str]:
    return {"service": "ml-models", "status": "ok"}


@app.post("/internal/ml/enrich")
def enrich_endpoint(request: EnrichRequest) -> dict[str, Any]:
    try:
        return enrich_evidence(request.snapshot)
    except (ValueError, KeyError) as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@app.post("/internal/ml/evaluate")
def evaluate_endpoint(request: EvaluateRequest) -> dict[str, Any]:
    try:
        return evaluate_snapshot(request.snapshot, request.evaluation)
    except (ValueError, KeyError) as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
