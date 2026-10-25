"""Evidence references for the assessment summary, built from the collected evidence itself.

No language model is involved: each claim restates a figure that is already in the snapshot
and points at the evidence row that holds it. Absences ("no land record is integrated") are
not cited, because there is nothing to cite. Uploaded documents are referenced only where an
identifier the user entered actually appears in the extracted text, by filename and page.
"""

from __future__ import annotations

import re
from typing import Any


PAGE_BREAK = "\f"  # backend-api joins extracted PDF pages with a form feed

CHANGE_WORDS = {
    "no_change": "no material land-cover change between same-season images a year apart",
    "inconclusive": "an inconclusive land-cover change signal (same-season images disagree)",
    "construction_growth": "land-cover change consistent with construction",
    "vegetation_loss": "vegetation loss",
    "vegetation_gain": "vegetation gain",
}


def _section(record: dict[str, Any], name: str) -> dict[str, Any]:
    value = record.get(name)
    return value if isinstance(value, dict) else {}


def _survey_pattern(survey: str, subdivision: str | None) -> re.Pattern[str]:
    """'123' + '4A' matches '123/4A', '123-4A', '123 / 4 A'. A bare number only after a survey-number label,
    since '123' alone appears in any document."""
    def loose(value: str) -> str:
        return r"\s*".join(re.escape(ch) for ch in value.replace(" ", ""))
    if subdivision:
        return re.compile(rf"(?<![\w/]){loose(survey)}\s*[/\-]\s*{loose(subdivision)}(?![\w/])", re.IGNORECASE)
    return re.compile(rf"(?:survey|s\.?\s*f?\.?)\s*no\.?\s*[:.\-]?\s*{loose(survey)}(?![\w/])", re.IGNORECASE)


def find_mentions(text: str, details: dict[str, Any]) -> list[dict[str, Any]]:
    """Where the user's survey number and village appear in one document, by page (1-based)."""
    pages = text.split(PAGE_BREAK) if PAGE_BREAK in text else [text]
    paged = PAGE_BREAK in text
    checks = []
    if details.get("survey_number"):
        value = details["survey_number"] + (f"/{details['subdivision']}" if details.get("subdivision") else "")
        checks.append(("survey_number", value, _survey_pattern(details["survey_number"], details.get("subdivision"))))
    if details.get("village"):
        checks.append(("village", details["village"], re.compile(rf"\b{re.escape(details['village'])}\b", re.IGNORECASE)))
    mentions = []
    for field, value, pattern in checks:
        hits = [index + 1 for index, page in enumerate(pages) if pattern.search(page)]
        if hits:
            mentions.append({"field": field, "value": value, "pages": hits if paged else None})
    return mentions


def land_details(supplied: dict[str, Any] | None, documents: list[dict[str, Any]] | None) -> dict[str, Any] | None:
    """The user's identifiers and documents, with where each identifier appears. Always unverified."""
    if not supplied and not documents:
        return None
    details = {key: value for key, value in (supplied or {}).items() if key != "documents"}
    texts = {str(doc.get("source_reference")): str(doc.get("text") or "") for doc in documents or []}
    listed = (supplied or {}).get("documents") or [
        {"filename": name, "doc_type": None, "text_extracted": bool(text)} for name, text in texts.items()
    ]
    details["documents"] = [
        {**doc, "mentions": find_mentions(texts.get(doc["filename"], ""), details)} for doc in listed
    ]
    details["verification_status"] = "user_provided_unverified"
    return details


def _first_sentence(text: str | None) -> str | None:
    if not text:
        return None
    return text.split(". ")[0].rstrip(".") + "."


def evidence_citations(record: dict[str, Any], factors: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """One citation per figure the assessment relies on, pointing at the evidence row that holds it."""
    rows = {}
    for row in record.get("evidence") or []:
        if isinstance(row, dict) and row.get("evidence_id"):
            rows[row["evidence_id"].rsplit(":", 1)[-1] if not row["evidence_id"].startswith("upload:")
                 else row["evidence_id"]] = row
    citations: list[dict[str, Any]] = []

    def cite(claim: str | None, key: str, location: str | None = None) -> None:
        row = rows.get(key)
        if claim and row:
            citations.append({"claim": claim, "source_type": row.get("source_type"),
                              "source_reference": row.get("source_reference"),
                              "evidence_id": row.get("evidence_id"), "location": location})

    by_factor = {factor["factor"]: factor for factor in factors}
    access = by_factor.get("accessibility") or {}
    parts = access.get("details") or {}
    if access.get("score") is not None and parts:
        road, school = parts["road"], parts["school"]

        def where(part: dict[str, Any]) -> str:
            return (f"{part['distance_m']:,.0f} m from the {part['measured_from']}" if part["distance_m"] is not None
                    else part["measured_from"])
        cite(f"Accessibility {access['score']:.0f}/100: nearest mapped road {where(road)}, nearest mapped school "
             f"{where(school)} (straight-line).", "osm")

    growth = by_factor.get("growth") or {}
    if growth.get("status") in ("indicative", "established"):
        cite(growth["basis"].split(". Further out")[0].rstrip(".") + ".", "land-cover")

    flood = _section(record, "flood_indicators")
    river = _section(flood, "river_flood")
    if river.get("status") in ("assessed", "partial"):
        cite(_first_sentence(next((row.get("summary") for key, row in rows.items() if key == "river-flood"), None)),
             "river-flood")
    water = _section(flood, "surface_water")
    if water.get("parcel") and water.get("within_buffer"):
        inside, around = water["parcel"], water["within_buffer"]
        if inside.get("water_ever_fraction") is not None and around.get("water_ever_fraction") is not None:
            cite(f"Open water was seen at least once (1984-2021) on {inside['water_ever_fraction'] * 100:.1f}% of the "
                 f"parcel's pixels and {around['water_ever_fraction'] * 100:.1f}% of pixels in the parcel and the "
                 f"{water.get('buffer_m', 500):.0f} m around it.", "surface-water")
    terrain = _section(flood, "terrain")
    if terrain.get("elevation_above_nearest_water_m") is not None:
        cite(f"The parcel's median ground is {terrain['elevation_above_nearest_water_m']:+.1f} m relative to the nearest "
             f"mapped water ({terrain.get('nearest_water_feature_name') or terrain.get('nearest_water_feature_class')}, "
             f"{terrain['nearest_water_feature_distance_m']:,.0f} m away).", "water-features")

    satellite = _section(record, "satellite")
    # Only the seasonal test (v2) supports these words; a v1 snapshot's trend label is not restated as a finding.
    if satellite.get("change_method") and satellite.get("change_type") in CHANGE_WORDS:
        cite(f"Satellite imagery shows {CHANGE_WORDS[satellite['change_type']]}.", "statistical-change")

    for doc in (_section(record, "user_land_details").get("documents") or []):
        for mention in doc.get("mentions") or []:
            pages = mention.get("pages")
            cite(f"{mention['field'].replace('_', ' ').capitalize()} {mention['value']} appears in your document "
                 f"{doc['filename']} (user-provided, not verified).", f"upload:{doc['filename']}",
                 f"page {', '.join(map(str, pages))}" if pages else None)
    return citations
