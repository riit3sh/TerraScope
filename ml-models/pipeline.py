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
from findings import build_findings
from citations import evidence_citations
from land_analyst import ai_provider, ask_land_question, generate_evaluation_explanation
from scoring_engine.scoring import compute_evaluation


LOGGER = logging.getLogger(__name__)
app = FastAPI(title="TerraScope ML Pipeline")


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


def _section(record: dict[str, Any], name: str) -> dict[str, Any]:
    value = record.get(name)
    return value if isinstance(value, dict) else {}


def evaluate_snapshot(snapshot: dict[str, Any], evaluation: dict[str, Any]) -> dict[str, Any]:
    """Evaluate an immutable evidence snapshot without collection connectors."""
    evaluated = deepcopy(snapshot)
    # Legacy request payloads may still contain document fields. Ignore them so
    # evaluation never turns an upload or sample corpus into parcel evidence.
    evaluated.pop("rag_documents", None)
    evaluated.pop("uploaded_documents", None)
    user_land_details = evaluated.pop("user_land_details", None)
    if isinstance(user_land_details, dict):
        user_land_details = {key: value for key, value in user_land_details.items() if key != "documents"}
        user_land_details.setdefault("verification_status", "user_provided_unverified")
        evaluated["user_land_details"] = user_land_details
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
        "red_flags": result["red_flags"],
        "pre_purchase_checks": result["pre_purchase_checks"],
        "would_change": result["would_change"],
        "findings": build_findings(evaluated, result["factors"]),
        # The AI summary must give the verdict's real reason; a map-only public-land hold was invisible to it.
        "government_land": result["government_land"],
    }
    # Every figure the assessment relies on, cited to the evidence row that holds it. No LLM needed.
    citations = evidence_citations(evaluated, result["factors"])
    # Groq explains the deterministic result; it never computes or changes the scores.
    ai_explanation: dict[str, Any] = {"answer_text": "", "citations": []}
    try:
        ai_explanation = generate_evaluation_explanation(evaluated)
    except Exception as error:
        LOGGER.warning("AI explanation unavailable; showing the deterministic summary: %s", error)
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
        "red_flags": result["red_flags"],
        "pre_purchase_checks": result["pre_purchase_checks"],
        "would_change": result["would_change"],
        "findings": evaluated["verdict"]["findings"],
        "government_land": result["government_land"],
        "development_outlook": result["development_outlook"],
    }
    _validate_snapshot(evaluated)
    return evaluated


class EnrichRequest(BaseModel):
    snapshot: dict[str, Any]


class EvaluateRequest(BaseModel):
    snapshot: dict[str, Any]
    evaluation: dict[str, Any]


class AskRequest(BaseModel):
    snapshot: dict[str, Any]
    question: str


@app.get("/health")
def health() -> dict[str, str]:
    # Safe operational visibility: report configuration presence, never the key.
    provider = ai_provider()
    return {
        "service": "ml-models",
        "status": "ok",
        "ai_provider": provider["name"] if provider else "none",
        "ai_model": provider["model"] if provider else "",
    }


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


@app.post("/internal/ml/ask")
def ask_endpoint(request: AskRequest) -> dict[str, Any]:
    try:
        return ask_land_question(request.snapshot, request.question)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    except RuntimeError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    except Exception as error:
        LOGGER.warning("Land Analyst request failed: %s", error)
        raise HTTPException(status_code=502, detail="TerraScope Land Analyst is temporarily unavailable.") from error
