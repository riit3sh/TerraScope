"""TerraScope Land Analyst: strict AI explanations over collected parcel facts (DeepInfra or Groq)."""

from __future__ import annotations

import os
import json
import math
import re
import time
import unicodedata
from typing import Any

import requests


GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"
DEEPINFRA_API_URL = "https://api.deepinfra.com/v1/openai/chat/completions"
DEEPINFRA_DEFAULT_MODEL = "openai/gpt-oss-20b"  # ~2 s and accurate in a 2026-10-28 comparison on a saved report
_PLACEHOLDER_KEYS = ("", "demo-groq-api-key")


def ai_provider() -> dict[str, str] | None:
    """The configured chat API: DeepInfra when DEEPINFRA_API_KEY is set, else Groq; None without a real key."""
    deepinfra_key = os.getenv("DEEPINFRA_API_KEY", "").strip()
    if deepinfra_key:
        return {"name": "DeepInfra", "url": DEEPINFRA_API_URL, "key": deepinfra_key,
                "model": os.getenv("DEEPINFRA_MODEL") or DEEPINFRA_DEFAULT_MODEL}
    groq_key = os.getenv("GROQ_API_KEY", "").strip()
    if groq_key not in _PLACEHOLDER_KEYS:
        return {"name": "Groq", "url": GROQ_API_URL, "key": groq_key,
                "model": os.getenv("GROQ_MODEL") or "llama-3.3-70b-versatile"}
    return None


# AI output is optional decoration on a deterministic verdict, so a slow provider
# must degrade, never stall the report.
EXPLANATION_TIMEOUT_SECONDS = float(os.getenv("GROQ_EXPLANATION_TIMEOUT_SECONDS", "12"))
# Free Groq tiers allow ~8k tokens a minute, so two calls close together get a 429.
# Wait out a short reset (Groq reports it); a longer one is reported to the user instead.
MAX_RATE_LIMIT_WAIT_SECONDS = float(os.getenv("GROQ_MAX_RATE_LIMIT_WAIT_SECONDS", "25"))
# Large raw series in the snapshot; their findings are already in the evidence summaries.
_BULKY_SATELLITE_KEYS = ("observations", "collection", "change_method")
EVIDENCE_SUMMARY_CHARS = 350
_VERDICT_KEYS = ("recommendation", "reasoning_summary", "red_flags", "pre_purchase_checks", "would_change")
_SCORE_KEYS = ("legal_safety_score", "accessibility_score", "flood_safety_score", "growth_score", "composite_score")


class GroqRateLimited(RuntimeError):
    """Groq's per-minute quota is used up; retrying later will work."""


def _extract_text(response: dict[str, Any]) -> str:
    choices = response.get("choices") or []
    message = choices[0].get("message", {}) if choices else {}
    return str(message.get("content", ""))


def _reset_seconds(response: requests.Response) -> float:
    """Seconds until Groq's quota resets, from retry-after or x-ratelimit-reset-tokens ('1m2.5s', '577ms')."""
    retry_after = response.headers.get("retry-after")
    if retry_after and retry_after.replace(".", "", 1).isdigit():
        return float(retry_after)
    match = re.fullmatch(r"(?:(\d+)m)?(?:([\d.]+)s)?(?:([\d.]+)ms)?", response.headers.get("x-ratelimit-reset-tokens", ""))
    if match and any(match.groups()):
        minutes, seconds, millis = (float(part) if part else 0.0 for part in match.groups())
        return minutes * 60 + seconds + millis / 1000
    return 5.0


def _groq_json(provider: dict[str, str], payload: dict[str, Any], max_wait: float = MAX_RATE_LIMIT_WAIT_SECONDS) -> dict[str, Any]:
    """POST to the provider and return the parsed JSON object it wrote, retrying a short 429 wait and one empty/invalid answer."""
    payload = {**payload, "model": provider["model"]}
    if provider["name"] != "Groq":
        payload.pop("include_reasoning", None)  # Groq-only; DeepInfra returns no reasoning text by default
        if "gpt-oss" not in provider["model"]:
            payload.pop("reasoning_effort", None)
    waited = 0.0
    bad_answers = 0
    while True:
        response = requests.post(
            provider["url"],
            headers={"Authorization": f"Bearer {provider['key']}", "Content-Type": "application/json"},
            json=payload,
            timeout=EXPLANATION_TIMEOUT_SECONDS,
        )
        if response.status_code == 429:
            wait = _reset_seconds(response) + 0.5
            if waited + wait > max_wait:
                raise GroqRateLimited(f"TerraScope Land Analyst is busy (AI rate limit). Try again in about {math.ceil(wait)} seconds.")
            time.sleep(wait)
            waited += wait
            continue
        response.raise_for_status()
        try:
            parsed = json.loads(_extract_text(response.json()))
            if isinstance(parsed, dict):
                return parsed
        except (json.JSONDecodeError, TypeError, ValueError):
            pass
        bad_answers += 1
        if bad_answers > 1:
            raise RuntimeError("Land Analyst returned an invalid response")


def generate_evaluation_explanation(snapshot: dict[str, Any]) -> dict[str, Any]:
    """Ask Groq to explain an already-computed evaluation using supplied facts only."""
    provider = ai_provider()
    if provider is None:
        raise RuntimeError("A real DEEPINFRA_API_KEY or GROQ_API_KEY is required for AI evaluation explanations.")

    breakdown = snapshot.get("score_breakdown") or {}
    evidence_rows = [row for row in snapshot.get("evidence", []) if isinstance(row, dict) and row.get("source_reference")]
    not_assessed = [str(row.get("title") or row["source_reference"]) for row in evidence_rows if _not_assessed(row)]
    factual_context = {
        # Keep the prompt compact. Sending the full raw snapshot made the model
        # spend its completion budget reasoning over implementation metadata and
        # return no explanation at all.
        "place": place_name(snapshot),
        "main_reason": main_reason(snapshot),
        "location": snapshot.get("location"),
        "not_assessed": not_assessed,
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
        _fold(str(row.get("source_reference"))): str(row.get("source_reference"))
        for row in snapshot.get("evidence", [])
        if isinstance(row, dict) and row.get("source_reference")
    }
    source_type_rows: dict[str, list[str]] = {}
    for row in snapshot.get("evidence", []):
        if isinstance(row, dict) and row.get("source_reference") and row.get("title"):
            source_aliases[_fold(str(row["title"]))] = str(row["source_reference"])
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
        "If a fact is missing, say that the evidence is unavailable. "
        "State the recommendation and its main_reason in plain words; never give a different reason for it. "
        "Area growth is past building only: describe how built-up the area is and its pace as its basis says; never "
        "call it growth potential or predict future growth. "
        "Everything in not_assessed was NOT checked: say it was not assessed; never say nothing was found, no hazard "
        "was found, or that it is safe. Refer to the plot by its place name (place), never by coordinates. "
        "A sentence about something with no evidence row (legal records, a check that was not assessed) gets no citation; "
        "never cite an unrelated source for it. Return JSON only in this shape: "
        '{"answer_text":"2-4 concise sentences","citations":[{"claim":"one factual claim","source_reference":"exact evidence_sources value"}]}. '
        "Do not put factor names, JSON keys, or prose such as 'scores' in source_reference.\n\n"
        "Allowed source references (copy exactly):\n"
        + "\n".join(f"- {source}" for source in source_aliases.values())
        + "\n\n"
        f"FACTS:\n{json.dumps(factual_context, ensure_ascii=True, default=str)}"
    )
    request = {"max_completion_tokens": 1200, "temperature": 0, "include_reasoning": False, "reasoning_effort": "low",
               "response_format": {"type": "json_object"}, "messages": [{"role": "user", "content": prompt}]}
    try:
        # max_wait=0: never hold up a report; the deterministic summary is shown instead.
        structured = _groq_json(provider, request, max_wait=0)
        if not structured.get("citations"):
            # About one answer in five came back with no citations at all (gpt-oss-20b, 2026-10-28); one retry
            # (~2 s) almost always fixes it, and an uncited answer is still never shown.
            structured = _groq_json(provider, request, max_wait=0)
    except GroqRateLimited:
        raise
    except RuntimeError:
        # A non-JSON answer is not safe to present as grounded; keep the
        # deterministic explanation instead of trying to infer citations.
        raise RuntimeError("Groq explanation was not valid JSON; deterministic explanation retained.")
    answer_text = str(structured.get("answer_text") or "").strip()
    citations: list[dict[str, str]] = [
        {"claim": str(item.get("claim") or "").strip(), "source_reference": str(item.get("source_reference") or "").strip()}
        for item in (structured.get("citations") or [])
        if isinstance(item, dict)
    ]
    normalized_citations, invalid = [], []
    for citation in citations:
        reference = _fold(citation["source_reference"])
        canonical = next(
            (source for alias, source in source_aliases.items() if reference == alias or reference in alias or alias in reference),
            None,
        )
        if canonical:
            normalized_citations.append({**citation, "source_reference": canonical})
        elif _is_factor_name(reference):
            # A factor name ("legal_safety") is not a source: the claim keeps its text, uncited. Any other unknown
            # source may be invented, so it still rejects the explanation below.
            continue
        else:
            invalid.append(citation["source_reference"])
    if invalid:
        raise RuntimeError(
            "Groq explanation cited a source that was not in the collected evidence "
            f"({invalid!r}); deterministic explanation retained."
        )
    # A claim cited to a row it shares no words with (legal status cited to Sentinel-2) keeps its text, loses the citation.
    rows_by_reference = {}
    for row in evidence_rows:
        rows_by_reference.setdefault(str(row["source_reference"]), []).append(row)
    normalized_citations = [citation for citation in normalized_citations
                            if _relevant(citation["claim"], rows_by_reference.get(citation["source_reference"], []))]
    if not normalized_citations:
        raise RuntimeError("Groq explanation contained no relevant source citations; deterministic explanation retained.")
    if any(_claims_nothing_found(answer_text, title) for title in not_assessed):
        raise RuntimeError("AI explanation described an unassessed check as clear; deterministic explanation retained.")
    return {"answer_text": _clip_sentences(answer_text, 900), "citations": normalized_citations}


_NOT_ASSESSED = re.compile(r"\b(not assessed|unavailable|not integrated|did not respond|could not be read)\b", re.I)
_FACTOR_KEYS = {"accessibility", "scores", "factors", "verdict", "recommendation", "legal", "flood", "growth"}
_STOPWORDS = {"which", "there", "their", "these", "those", "parcel", "about", "within", "would", "because", "where",
              "based", "other", "being", "plot's", "parcel's"}


def _is_factor_name(reference: str) -> bool:
    """'legal_safety', 'legal_safety factor', 'accessibility score': a JSON key or factor, not a source."""
    words = reference.split()
    return (1 <= len(words) <= 2 and bool(re.fullmatch(r"[a-z_]+", words[0]))
            and ("_" in words[0] or words[0] in _FACTOR_KEYS) and (len(words) == 1 or words[1] in ("factor", "score")))


def _not_assessed(row: dict[str, Any]) -> bool:
    return bool(_NOT_ASSESSED.search(str(row.get("summary") or "")[:200]))


def _fold(text: str) -> str:
    """Case- and Unicode-insensitive form: models write narrow no-break spaces and non-breaking hyphens."""
    return " ".join(unicodedata.normalize("NFKC", text).replace("\u2010", "-").casefold().split())


def _words(text: str) -> set[str]:
    return {word for word in re.findall(r"[a-z][a-z0-9'-]{4,}", _fold(text)) if word not in _STOPWORDS}


def _relevant(claim: str, rows: list[dict[str, Any]]) -> bool:
    claim_words = _words(claim)
    if not claim_words:  # an empty or numbers-only claim cannot be judged: keep the citation
        return True
    row_text = " ".join(f"{row.get('title') or ''} {row.get('summary') or ''} {row.get('source_type') or ''}" for row in rows)
    return bool(claim_words & _words(row_text))


def _claims_nothing_found(answer: str, title: str) -> bool:
    """'no river flood hazard was found' when the river flood maps were never read."""
    if "flood" not in title.casefold():
        return False
    return bool(re.search(r"\bno (?:\w+ ){0,2}flood\w*(?: (?:hazard|risk|exposure|inundation))?\s*(?:was |were |is )?"
                          r"(?:found|detected|identified|modell?ed|shown)", answer, re.I))


def _clip_sentences(text: str, limit: int) -> str:
    """At most ``limit`` characters, ending at a whole sentence (never mid-word)."""
    if len(text) <= limit:
        return text
    cut = text[:limit]
    end = max(cut.rfind(". "), cut.rfind(".\n"), cut.rfind("? "), cut.rfind("! "))
    return cut[:end + 1] if end > 0 else cut[:cut.rfind(" ")].rstrip(",;:") + "…"


def main_reason(snapshot: dict[str, Any]) -> str | None:
    """Why the verdict is what it is, as the report's headline says it (frontend ReportSummary verdictHeadline)."""
    verdict = snapshot.get("verdict") or {}
    recommendation = verdict.get("recommendation")
    government = verdict.get("government_land") or {}
    factors = (snapshot.get("score_breakdown") or {}).get("factors") or []
    missing = [f["factor"] for f in factors if isinstance(f, dict) and f.get("factor") in ("growth", "accessibility")
               and f.get("status") == "unavailable"]
    if recommendation == "RESTRICTED":
        return "the boundary overlaps mapped restricted land, which TerraScope does not assess for purchase"
    if recommendation == "AVOID":
        return "a serious problem was found: " + str((verdict.get("red_flags") or ["see the red flags"])[0])
    if recommendation in ("WAIT", "INSUFFICIENT_EVIDENCE") and missing:
        return "TerraScope could not measure " + " or ".join(
            "the area's development history" if f == "growth" else "road access" for f in missing)
    if recommendation == "BUY":
        return "the location is strong, but ownership, loans on the land and approvals are not yet verified"
    if government.get("hold"):
        return ("the drawn boundary overlaps or touches mapped public land (" + str(government.get("label") or "map only")
                + "); this must be ruled out with official land records")
    if recommendation == "WAIT":
        return "the location evidence is not strong enough yet, and ownership and approvals are not verified"
    return None


def place_name(snapshot: dict[str, Any]) -> str | None:
    """The first part of the address ('Lancor Infinys'), or the district, for referring to the plot."""
    location = snapshot.get("location") or {}
    address = str(location.get("address") or "").strip()
    first = address.split(",")[0].strip() if address else ""
    if first and not first[:1].isdigit():
        return first
    return ", ".join(part.strip() for part in address.split(",")[:2]) or location.get("district") or None


def ask_land_question(snapshot: dict[str, Any], question: str) -> dict[str, Any]:
    """Answer one explicit question from the immutable snapshot only."""
    question = question.strip()
    if not question or len(question) > 500:
        raise ValueError("question must contain 1-500 characters")
    provider = ai_provider()
    if provider is None:
        raise RuntimeError("A real DEEPINFRA_API_KEY or GROQ_API_KEY is required for TerraScope Land Analyst.")
    # Keep the prompt near 1.5k tokens: Groq's per-minute quota counts every question.
    evidence = [
        {**{key: row.get(key) for key in ("source_reference", "title", "observed_at") if row.get(key) is not None},
         "summary": str(row.get("summary") or "")[:EVIDENCE_SUMMARY_CHARS]}
        for row in snapshot.get("evidence", []) if isinstance(row, dict)
    ]
    facts = {key: snapshot.get(key) for key in ("location", "geometry_metadata", "infrastructure", "risk", "satellite", "land_records", "rera", "opportunity", "evaluation", "verdict")}
    if isinstance(facts["satellite"], dict):
        facts["satellite"] = {key: value for key, value in facts["satellite"].items() if key not in _BULKY_SATELLITE_KEYS}
    if isinstance(facts["verdict"], dict):
        # The report's own answer, without the long findings and citation lists.
        facts["verdict"] = {key: facts["verdict"].get(key) for key in _VERDICT_KEYS}
    breakdown = snapshot.get("score_breakdown") or {}
    facts["scores"] = {key: breakdown.get(key) for key in _SCORE_KEYS if key in breakdown}
    facts = {key: value for key, value in facts.items() if value not in (None, {}, [])}
    facts["evidence"] = evidence
    allowed = [str(row.get("source_reference")) for row in evidence if row.get("source_reference")]
    prompt = (
        "You are TerraScope Land Analyst. Answer the user's question in at most 3 concise sentences. "
        "Use only the supplied parcel facts and evidence. Do not invent or infer missing values. Never claim title, "
        "ownership, encumbrance, RERA, zoning, legal access, flood safety, or price is verified unless the facts "
        "explicitly say it was verified by an official record. Say 'not available in this analysis' when insufficient. "
        "If asked whether to buy, state the report's recommendation from verdict.recommendation and its main reasons; "
        "it is TerraScope's rule-based answer, not your own advice. answer_text must never be empty. "
        "Cite factual claims with [source: X], where X is copied exactly from an allowed source reference. Return JSON only: "
        "{\"answer_text\":\"...\",\"citations\":[{\"claim\":\"...\",\"source_reference\":\"...\"}]}\n\n"
        f"Allowed source references: {json.dumps(allowed)}\nQuestion: {question}\nFacts: {json.dumps(facts, ensure_ascii=True, default=str)}"
    )
    request = {"max_completion_tokens": 500, "temperature": 0, "include_reasoning": False,
               "reasoning_effort": "low", "response_format": {"type": "json_object"},
               "messages": [{"role": "user", "content": prompt}]}
    payload = _groq_json(provider, request)
    if not str(payload.get("answer_text") or "").strip():
        # An empty answer showed as a blank panel; ask once more, then say so plainly.
        payload = _groq_json(provider, request)
        if not str(payload.get("answer_text") or "").strip():
            raise RuntimeError("TerraScope Land Analyst could not answer that; try rephrasing the question.")
    citations = []
    for item in payload.get("citations") or []:
        if not isinstance(item, dict):
            continue
        reference = str(item.get("source_reference") or "").strip()
        canonical = next((source for source in allowed if reference.casefold() == source.casefold()), None)
        if canonical:
            citations.append({"claim": str(item.get("claim") or "").strip(), "source_reference": canonical})
    return {"answer_text": str(payload.get("answer_text") or "").strip()[:1000], "citations": citations}
