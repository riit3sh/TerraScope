"""Grounded Groq reasoning over parcel-scoped retrieved context."""

from __future__ import annotations

import os
import re
import json
from typing import Any

import requests


GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"
MODEL_NAME = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
SOURCE_TAG_PATTERN = re.compile(r"\[source:\s*([^\]]+)\]")
# AI output is optional decoration on a deterministic verdict, so these stay well
# inside the caller's budget: a slow Groq must degrade, never stall the report.
GROUNDED_TIMEOUT_SECONDS = float(os.getenv("GROQ_GROUNDED_TIMEOUT_SECONDS", "15"))
EXPLANATION_TIMEOUT_SECONDS = float(os.getenv("GROQ_EXPLANATION_TIMEOUT_SECONDS", "12"))


def _prompt(question: str, context: list[dict[str, Any]]) -> str:
    context_text = "\n\n".join(
        f"[source: {item['metadata']['source_reference']}]\n{item['text']}"
        for item in context
    )
    if not context_text:
        context_text = "[source: none]\nNo retrieved context is available."
    return (
        "Answer ONLY using the provided context. Cite every claim with [source: X]. "
        "If the context is insufficient, say so explicitly.\n\n"
        f"Context:\n{context_text}\n\n"
        f"Question: {question}"
    )


def _extract_text(response: dict[str, Any]) -> str:
    choices = response.get("choices") or []
    message = choices[0].get("message", {}) if choices else {}
    return str(message.get("content", ""))


def _parse_citations(answer_text: str) -> list[dict[str, str]]:
    citations: list[dict[str, str]] = []
    for claim in re.split(r"(?<=[.!?])\s+|\n+", answer_text):
        references = SOURCE_TAG_PATTERN.findall(claim)
        clean_claim = SOURCE_TAG_PATTERN.sub("", claim).strip()
        if not clean_claim:
            continue
        for reference in references:
            citation = {"claim": clean_claim, "source_reference": reference.strip()}
            if citation not in citations:
                citations.append(citation)
    return citations


def generate_grounded_answer(question: str, parcel_id: str) -> dict[str, Any]:
    """Retrieve parcel context and ask Groq for a source-tagged answer."""
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        raise RuntimeError("GROQ_API_KEY must be set to generate a grounded answer.")
    # Imported here, not at module load: retrieval pulls in chromadb and torch
    # (~10-35 s cold), which the evaluation explanation never needs. A failed
    # import (e.g. chromadb missing) still surfaces as itself.
    if __package__:
        from .retrieve import retrieve_context
    else:  # pragma: no cover - direct script execution.
        from retrieve import retrieve_context
    context = retrieve_context(question, parcel_id)
    response = requests.post(
        GROQ_API_URL,
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json={"model": MODEL_NAME, "max_completion_tokens": 700, "temperature": 0,
              "include_reasoning": False, "reasoning_effort": "low",
              "messages": [{"role": "user", "content": _prompt(question, context)}]},
        timeout=GROUNDED_TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    answer_text = _extract_text(response.json())
    return {"answer_text": answer_text, "citations": _parse_citations(answer_text)}


def generate_evaluation_explanation(snapshot: dict[str, Any]) -> dict[str, Any]:
    """Ask Groq to explain an already-computed evaluation using supplied facts only."""
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key or api_key == "demo-groq-api-key":
        raise RuntimeError("A real GROQ_API_KEY is required for AI evaluation explanations.")

    breakdown = snapshot.get("score_breakdown") or {}
    factual_context = {
        # Keep the prompt compact. Sending the full raw snapshot made the model
        # spend its completion budget reasoning over implementation metadata and
        # return no explanation at all.
        "location": snapshot.get("location"),
        "area_m2": (snapshot.get("geometry_metadata") or {}).get("area_m2"),
        "recommendation": (snapshot.get("verdict") or {}).get("recommendation"),
        "scores": {
            key: breakdown.get(key)
            for key in ("legal_safety_score", "accessibility_score", "flood_safety_score", "growth_score", "composite_score")
            if breakdown.get(key) is not None
        },
        "factors": [
            {
                key: factor.get(key)
                for key in ("factor", "status", "score", "basis", "limitations")
                if factor.get(key) is not None
            }
            for factor in breakdown.get("factors", [])
            if isinstance(factor, dict)
        ],
        "verdict": {
            key: snapshot.get("verdict", {}).get(key)
            for key in ("recommendation", "red_flags", "pre_purchase_checks", "would_change")
            if key in (snapshot.get("verdict") or {})
        },
        "evidence": [
            {
                key: row.get(key)
                for key in ("source_reference", "title", "summary", "observed_at", "freshness")
                if row.get(key) is not None
            }
            for row in snapshot.get("evidence", [])
            if isinstance(row, dict) and row.get("source_reference")
        ],
        "evidence_sources": [
            {
                "source_reference": row.get("source_reference"),
                "title": row.get("title"),
                "observed_at": row.get("observed_at"),
                "freshness": row.get("freshness"),
            }
            for row in snapshot.get("evidence", [])
            if isinstance(row, dict) and row.get("source_reference")
        ],
    }
    source_aliases = {
        str(row.get("source_reference")).casefold(): str(row.get("source_reference"))
        for row in snapshot.get("evidence", [])
        if isinstance(row, dict) and row.get("source_reference")
    }
    source_type_rows: dict[str, list[str]] = {}
    for row in snapshot.get("evidence", []):
        if isinstance(row, dict) and row.get("source_reference") and row.get("title"):
            source_aliases[str(row["title"]).casefold()] = str(row["source_reference"])
        if isinstance(row, dict) and row.get("source_reference") and row.get("source_type"):
            source_type_rows.setdefault(str(row["source_type"]).casefold(), []).append(str(row["source_reference"]))
    # A model sometimes returns the evidence type rather than the long source
    # label. Permit that only when the type identifies exactly one collected row;
    # ambiguous types remain invalid rather than being attached to the wrong fact.
    for source_type, references in source_type_rows.items():
        if len(references) == 1:
            source_aliases[source_type] = references[0]
    prompt = (
        "You are TerraScope Land Analyst. Explain the already-computed land assessment in 2-4 concise sentences. "
        "Use ONLY the JSON facts below. Never invent missing values, sources, dates, or legal conclusions. "
        "The numerical scores and recommendation are authoritative and must not be changed. "
        "Do not present a map signal as proof of ownership, title clearance, RERA registration, flood safety, or price. "
        "If the evidence is insufficient for a conclusion, say so explicitly instead of guessing. "
        "Cite each factual sentence with [source: X]. X MUST be copied exactly from one of the evidence_sources.source_reference values; "
        "do not cite a source type, a provider name, or a source that is not listed. "
        "If a fact is missing, say that the evidence is unavailable. Return JSON only in this shape: "
        '{"answer_text":"2-4 concise sentences","citations":[{"claim":"one factual claim","source_reference":"exact evidence_sources value"}]}. '
        "Do not put factor names, JSON keys, or prose such as 'scores' in source_reference.\n\n"
        "Allowed source references (copy exactly):\n"
        + "\n".join(f"- {source}" for source in source_aliases.values())
        + "\n\n"
        f"FACTS:\n{json.dumps(factual_context, ensure_ascii=True, default=str)}"
    )
    response = requests.post(
        GROQ_API_URL,
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json={"model": MODEL_NAME, "max_completion_tokens": 1200, "temperature": 0,
              "include_reasoning": False, "reasoning_effort": "low",
              "response_format": {"type": "json_object"},
              "messages": [{"role": "user", "content": prompt}]},
        timeout=EXPLANATION_TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    answer_text = _extract_text(response.json()).strip()
    citations: list[dict[str, str]]
    try:
        structured = json.loads(answer_text)
        if not isinstance(structured, dict):
            raise ValueError("not an object")
        answer_text = str(structured.get("answer_text") or "").strip()
        citations = [
            {"claim": str(item.get("claim") or "").strip(), "source_reference": str(item.get("source_reference") or "").strip()}
            for item in (structured.get("citations") or [])
            if isinstance(item, dict)
        ]
    except (json.JSONDecodeError, TypeError, ValueError):
        # Backwards-compatible fallback for a model that ignores JSON mode.
        citations = _parse_citations(answer_text)
    normalized_citations = []
    for citation in citations:
        reference = citation["source_reference"].casefold()
        canonical = next(
            (source for alias, source in source_aliases.items() if reference == alias or reference in alias or alias in reference),
            None,
        )
        if canonical:
            normalized_citations.append({**citation, "source_reference": canonical})
    if not normalized_citations:
        raise RuntimeError("Groq explanation contained no source citations; deterministic explanation retained.")
    if len(normalized_citations) != len(citations):
        invalid = [citation["source_reference"] for citation in citations if citation not in normalized_citations]
        raise RuntimeError(
            "Groq explanation cited a source that was not in the collected evidence "
            f"({invalid!r}); deterministic explanation retained."
        )
    return {"answer_text": answer_text[:500], "citations": normalized_citations}
