"""Grounded Groq reasoning over parcel-scoped retrieved context."""

from __future__ import annotations

import os
import re
from typing import Any

import requests

try:
    from .retrieve import retrieve_context
except ImportError:  # pragma: no cover - supports direct script execution.
    from retrieve import retrieve_context


GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"
MODEL_NAME = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
SOURCE_TAG_PATTERN = re.compile(r"\[source:\s*([^\]]+)\]")


def _prompt(question: str, context: list[dict[str, Any]]) -> str:
    context_text = "\n\n".join(
        f"[source: {item['metadata']['source_reference']}]\n{item['text']}"
        for item in context
    )
    return (
        "Answer ONLY using the provided context. Cite every claim with [source: X]. "
        "If the context is insufficient, say so explicitly.\n\n"
        f"Context:\n{context_text or '[source: none]\nNo retrieved context is available.'}\n\n"
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
    context = retrieve_context(question, parcel_id)
    response = requests.post(
        GROQ_API_URL,
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json={"model": MODEL_NAME, "max_tokens": 700, "temperature": 0, "messages": [{"role": "user", "content": _prompt(question, context)}]},
        timeout=60,
    )
    response.raise_for_status()
    answer_text = _extract_text(response.json())
    return {"answer_text": answer_text, "citations": _parse_citations(answer_text)}
