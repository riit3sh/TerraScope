"""Pure ML-stage enrichment and evaluation pipeline for TerraScope."""

from __future__ import annotations

import hashlib
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
from citations import PAGE_BREAK, evidence_citations, land_details
from scoring_engine.scoring import compute_evaluation


LOGGER = logging.getLogger(__name__)
app = FastAPI(title="TerraScope ML Pipeline")
_RAG_CACHE: dict[tuple[str, str, str], dict[str, Any]] = {}


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
        if not (isinstance(item, dict) and item.get("evidence_id", "").endswith(":statistical-change"))
    ]
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    method = change["change_method"]
    medians = (
        f" Median same-season change: NDVI {method['median_ndvi_change']:+.3f}, NDBI {method['median_ndbi_change']:+.3f}."
        if method.get("median_ndvi_change") is not None else ""
    )
    evidence.append({
        "evidence_id": f"{enriched.get('metadata', {}).get('analysis_snapshot_id', 'snapshot')}:statistical-change",
        "source_type": "derived",
        "source_reference": method["method"],
        "title": "Land-cover change test (same season, a year apart)",
        "observed_at": now,
        "freshness": "derived",
        "summary": (
            f"Result: {change['change_type'].replace('_', ' ')}. {method['pairs']} same-season pair(s) from "
            f"{method['observations']} observations.{medians} {method['reason']} Fixed rule thresholds "
            f"(stable within ±{method['stable_limit']}, change from {method['change_limit']}), not calibrated "
            "against labelled change, so no confidence percentage is given."
        ),
    })
    enriched["evidence"] = evidence
    _validate_snapshot(enriched)
    return enriched


def _documents_fingerprint(documents: list[dict[str, Any]]) -> str:
    """Stable digest of the retrieval corpus, so new uploads invalidate cached answers."""
    digest = hashlib.sha256()
    for document in sorted(documents, key=lambda item: str(item.get("source_reference") or "")):
        digest.update(str(document.get("source_reference") or "").encode("utf-8"))
        digest.update(b"|ref|")
        digest.update(str(document.get("text") or "").encode("utf-8"))
        digest.update(b"|end|")
    return digest.hexdigest()


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
    # The document set is part of the key: uploading new evidence after an earlier
    # evaluation changes neither the snapshot id nor the question, so keying on
    # those alone would serve an answer that never saw the new upload.
    cache_key = (
        str(snapshot.get("metadata", {}).get("analysis_snapshot_id", parcel_id)),
        question,
        _documents_fingerprint(documents),
    )
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


def _with_document_evidence(
    evidence: list[dict[str, Any]],
    documents: list[dict[str, Any]] | None,
) -> list[dict[str, Any]]:
    """Add one ledger row per uploaded document so the report can show what was attached."""
    rows = [item for item in evidence if not (isinstance(item, dict) and item.get("source_type") == "user_upload")]
    if not documents:
        return rows
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    seen: set[str] = set()
    for document in documents:
        reference = str(document.get("source_reference") or "uploaded document")
        if reference in seen:
            continue
        seen.add(reference)
        text = str(document.get("text") or "")
        pages = text.count(PAGE_BREAK) + 1 if PAGE_BREAK in text else None
        rows.append({
            "evidence_id": f"upload:{reference}",
            "source_type": "user_upload",
            "source_reference": reference,
            "title": "Your uploaded document (user-provided, not verified)",
            "observed_at": now,
            "freshness": "user_upload",
            "summary": (
                f"{len(text.split())} words extracted" + (f" from {pages} pages" if pages else "")
                + ". TerraScope searches it for the survey number and village you entered and cites the page where "
                "they appear. Finding them there does not verify ownership, encumbrance or approval."
                + (" It is also available to the AI explanation." if os.getenv("GROQ_API_KEY") else "")
            ),
        })
    return rows


def _section(record: dict[str, Any], name: str) -> dict[str, Any]:
    value = record.get(name)
    return value if isinstance(value, dict) else {}


def evaluate_snapshot(snapshot: dict[str, Any], evaluation: dict[str, Any]) -> dict[str, Any]:
    """Evaluate an immutable evidence snapshot without collection connectors."""
    evaluated = deepcopy(snapshot)
    # These are request-scoped RAG inputs, never persisted evidence-schema fields.
    rag_documents = evaluated.pop("rag_documents", None)
    uploaded_documents = evaluated.pop("uploaded_documents", None)
    documents = rag_documents if rag_documents is not None else uploaded_documents
    evaluated["evidence"] = _with_document_evidence(evaluated.get("evidence") or [], documents)
    # The user's survey identifiers and document types: request-scoped claims, never land_records.
    evaluated["user_land_details"] = land_details(evaluated.pop("user_land_details", None), documents)
    evaluated["evaluation"] = deepcopy(evaluation)
    result = compute_evaluation(evaluated, evaluation)
    risk = evaluated.setdefault("risk", {}) or {}
    # An unassessed factor stays null everywhere; it is never back-filled with a
    # derived number, because that is what made unknowns look like real scores.
    legal = result["legal_safety_score"]
    risk["legal_risk_score"] = round(100.0 - legal, 2) if legal is not None else None
    risk["flood_assessment_status"] = "assessed" if result["flood_safety_score"] is not None else "unavailable"
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
            "factors",
            "assessed_weight_pct",
            "unassessed_factors",
        )
    }
    # Include the authoritative rule-based verdict in the facts sent to Groq.
    evaluated["verdict"] = {
        "recommendation": result["recommendation"],
        "confidence": result["confidence"],  # deliberately null: see scoring_engine
        "reasoning_summary": result["reasoning_summary"],
        "citations": [],
    }
    # Every figure the assessment relies on, cited to the evidence row that holds it. No LLM needed.
    citations = evidence_citations(evaluated, result["factors"])
    # Groq explains the deterministic result; it never computes or changes the scores.
    ai_explanation: dict[str, Any] = {"answer_text": "", "citations": []}
    try:
        from rag_pipeline.reason import generate_evaluation_explanation

        ai_explanation = generate_evaluation_explanation(evaluated)
    except Exception as error:
        LOGGER.info("AI explanation not used; showing the deterministic summary: %s", error)
    citations.extend(
        {
            "claim": citation["claim"],
            "source_type": "rag",
            "source_reference": citation["source_reference"],
        }
        for citation in _maybe_grounded_reasoning(evaluated, documents)
    )
    citations.extend(
        {
            "claim": citation["claim"],
            "source_type": "ai_explanation",
            "source_reference": citation["source_reference"],
        }
        for citation in ai_explanation.get("citations", [])
    )
    ai_text = ai_explanation.get("answer_text")
    evaluated["verdict"] = {
        "recommendation": result["recommendation"],
        "confidence": result["confidence"],  # deliberately null: see scoring_engine
        "reasoning_summary": ai_text or result["reasoning_summary"],
        # Says who wrote reasoning_summary, so the report never labels rule output as AI.
        "explanation_source": "ai" if ai_text else "deterministic",
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
