"""Evidence gates for TerraScope scoring.

A score is only emitted when evidence actually supports it. Missing evidence
stays unknown: it is never substituted with 50, and it is never silently dropped
so that the surviving factors renormalise into a better-looking result.
"""

from __future__ import annotations

import unicodedata
from typing import Any


LEGAL_EVIDENCE_CHECKLIST = (
    "Ownership record matched to this survey / subdivision number",
    "Encumbrance certificate or registered transaction history",
    "Land-use zoning approval or restriction record",
    "Project registration from the parcel's own state authority",
)

MISSING_FLOOD_EVIDENCE = {
    "river_flooding": "River flood hazard map covering this parcel, with resolution and date",
    "historical_inundation": "Observed historical inundation footprints for the parcel vicinity (a permitted machine-readable source)",
    "observed_surface_water": "Observed surface-water history for the parcel and its surroundings",
    "terrain_and_nearby_water": "Elevation relative to the nearest watercourse and drainage network",
    "rainfall_waterlogging": "Rainfall intensity and local drainage capacity, or a pluvial flood model",
    "coastal_flooding": "Storm-surge and sea-level inundation data (relevant near the coast)",
}

# What a growth score would need. Satellite indices are none of these.
GROWTH_EVIDENCE_CHECKLIST = (
    "Registered sale (transaction) counts and prices for the village or sub-registrar office over several years",
    "Master plan / local planning authority land-use zoning and approved layouts near the parcel",
    "Committed infrastructure (roads, rail, utilities) with sanction dates and distances",
    "Population and employment change for the town or taluk (Census / economic survey)",
)

FLOOD_EVIDENCE_CHECKLIST = (
    "Flood hazard / inundation extent map covering this parcel, with resolution and date",
    "Historical inundation records for the parcel vicinity",
    "Distance and elevation relative to the nearest watercourse and drainage network",
    "Rainfall intensity and local drainage capacity",
)


def _section(record: dict[str, Any], name: str) -> dict[str, Any]:
    value = record.get(name)
    return value if isinstance(value, dict) else {}


def _evidence_rows(record: dict[str, Any]) -> list[dict[str, Any]]:
    rows = record.get("evidence")
    return [row for row in rows if isinstance(row, dict)] if isinstance(rows, list) else []


def satellite_is_synthetic(record: dict[str, Any]) -> bool:
    """True when the satellite series was invented for demo mode."""
    for row in _evidence_rows(record):
        if row.get("source_type") != "satellite":
            continue
        label = f"{row.get('source_reference') or ''} {row.get('title') or ''}".lower()
        if "synthetic" in label or row.get("freshness") == "seed_data":
            return True
    return False


LAND_IDENTIFIER_FIELDS = ("state", "district", "taluk", "village", "survey_number", "subdivision")
DOC_TYPE_LABELS = {
    "patta_chitta": "patta / chitta (ownership record)",
    "encumbrance_certificate": "encumbrance certificate",
    "sale_deed": "sale deed",
    "layout_or_building_approval": "layout or building approval",
    "fmb_sketch": "FMB / survey sketch",
    "other": "other document",
}


def parcel_state(record: dict[str, Any]) -> str | None:
    """The geocoded state, else the boundary file's (polygon-based, so known even without an address)."""
    states = _section(record, "coverage").get("states") or []
    name = _section(record, "location").get("state") or (states[0].get("name") if len(states) == 1 else None)
    return unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode() if name else None


def supplied_summary(details: dict[str, Any]) -> str:
    """One honest sentence about what the user supplied: never 'verified'."""
    ids = {field: details.get(field) for field in LAND_IDENTIFIER_FIELDS if details.get(field)}
    parts = []
    if ids.get("survey_number"):
        survey = ids["survey_number"] + (f"/{ids['subdivision']}" if ids.get("subdivision") else "")
        place = ", ".join(ids[f] for f in ("village", "taluk", "district", "state") if ids.get(f))
        parts.append(f"You supplied survey {survey}" + (f" in {place}" if place else ""))
        missing = [f for f in ("state", "district", "village") if not ids.get(f)]
        if missing:
            parts.append(f"add the {', '.join(missing)}: survey numbers repeat across villages, so the identifier is ambiguous")
    documents = details.get("documents") or []
    if documents:
        listed = []
        for doc in documents:
            found = [f"{m['field'].replace('_', ' ')} on page {', '.join(map(str, m['pages']))}" if m.get("pages")
                     else f"{m['field'].replace('_', ' ')}" for m in doc.get("mentions") or []]
            listed.append(f"{doc['filename']} ({DOC_TYPE_LABELS.get(doc.get('doc_type'), 'type not given')}"
                          + (f"; mentions {', '.join(found)}" if found else "") + ")")
        parts.append("documents: " + "; ".join(listed))
    if not parts:
        return ""
    return "; ".join(parts) + ". These are user-provided and not independently verified, so title is not verified."


def land_records_matched(record: dict[str, Any]) -> bool:
    """True only when an authoritative record was actually retrieved and matched."""
    records = record.get("land_records")
    if not isinstance(records, dict):
        return False
    return any(
        records.get(field) is not None
        for field in ("survey_number", "ownership_type", "title_clear", "encumbrance_flag")
    )


def assess_legal(
    record: dict[str, Any],
    evaluation: dict[str, Any],
    legal_risk_score,
    apply_rera_requirement,
) -> dict[str, Any]:
    """Legal safety, or an explicit incomplete verification with a checklist.

    No ownership, encumbrance, restriction or state registration source is
    integrated. Absence of records is not evidence of clear title, so no number
    is produced from it.
    """
    if not land_records_matched(record):
        state = parcel_state(record) or "this parcel's state"
        supplied = _section(record, "user_land_details")
        basis = (
            "Legal verification incomplete: no authoritative land record was retrieved or matched for this parcel "
            f"({state}). Absence of records is not evidence of clear title."
        )
        if supplied:
            basis += " " + supplied_summary(supplied)
        return {
            "factor": "legal_safety",
            "score": None,
            "status": "unavailable",
            "basis": basis,
            "limitations": (
                "No ownership, encumbrance, restriction or land-use approval source is integrated, and no dataset "
                f"from the RERA authority for {state} is. Documents you upload are recorded as your claims: "
                "TerraScope can show where an identifier appears in them, but that never verifies title."
            ),
            "checklist": list(LEGAL_EVIDENCE_CHECKLIST),
            "details": supplied or None,
        }
    scoring_record = {**record, "evaluation": evaluation}
    risk = min(100.0, legal_risk_score(scoring_record) + apply_rera_requirement(record, evaluation)["penalty"])
    return {
        "factor": "legal_safety",
        "score": round(100.0 - risk, 2),
        "status": "assessed",
        "basis": f"Scored from matched land records; effective legal risk {risk:.1f}/100.",
        "limitations": "Project-registration matching is district-level and limited to the seeded state.",
        "checklist": [],
    }


def assess_flood(record: dict[str, Any]) -> dict[str, Any]:
    """Flood safety is scored only when a validated source populates risk.flood_risk_score.

    Nothing does today: the ETL leaves that field null. When per-mechanism flood
    evidence exists (modelled river flooding, observed surface water, terrain) the
    factor is "partial" with that evidence in its basis and NO score; otherwise it is
    "unavailable". The terrain-position indicator must never populate the score.
    """
    risk = _section(record, "risk")
    hazard = risk.get("flood_risk_score")
    if isinstance(hazard, (int, float)):
        return {
            "factor": "flood_safety",
            "score": round(max(0.0, min(100.0, 100.0 - float(hazard))), 2),
            "status": "assessed",
            "basis": risk.get("flood_risk_basis") or f"From an integrated flood hazard source (risk {hazard}/100).",
            "limitations": "Check the source's resolution, coverage and observation date.",
            "checklist": [],
        }
    indicators = _section(record, "flood_indicators")
    components = [c for c in (indicators.get("components") or []) if isinstance(c, dict)]
    usable = [c for c in components if c.get("status") in ("assessed", "partial")]
    if usable:
        # Real evidence for some mechanisms. It is shown, mechanism by mechanism, but no
        # validated method combines it into a safety score, so the score stays withheld
        # (and a missing mechanism can never be read as a perfect one).
        river = next((c for c in components if c.get("mechanism") == "river_flooding"), {})
        missing = [
            c["mechanism"].replace("_", " ") for c in components
            if c.get("status") not in ("assessed", "partial")
        ]
        # The flood panel carries the measurements; this line only says what was and was not assessed.
        head = ("River flood exposure assessed (modelled scenarios, ~90 m)" if river.get("status") in ("assessed", "partial")
                else "River flood exposure not assessed")
        others = [c["mechanism"].replace("_", " ") for c in usable if c.get("mechanism") != "river_flooding"]
        basis = head + ("; also measured: " + ", ".join(others) if others else "")
        basis += ("; other mechanisms incomplete (" + ", ".join(missing) + ")." if missing else ".")
        return {
            "factor": "flood_safety",
            "score": None,
            "status": "partial",
            "basis": basis,
            "limitations": (
                "No overall Flood Safety score: no validated method combines the mechanisms, and a mechanism that "
                "is not assessed is unknown, not safe. Measurements and caveats are in the flood section."
            ),
            # What is still missing, not a generic list that includes what was just measured.
            "checklist": [MISSING_FLOOD_EVIDENCE[c["mechanism"]] for c in components
                          if c.get("status") not in ("assessed", "partial") and c.get("mechanism") in MISSING_FLOOD_EVIDENCE],
        }
    return {
        "factor": "flood_safety",
        "score": None,
        "status": "unavailable",
        "basis": "No usable flood evidence was retrieved for this parcel: every flood source was unavailable or not integrated.",
        "limitations": (
            "Coastal, fluvial (river) and pluvial (rainfall/drainage) flooding are distinct and none is "
            "assessed here. Missing evidence is unknown, not safe. Being inland does not establish safety, and "
            "district flood history would not establish risk for this individual plot."
        ),
        "checklist": list(FLOOD_EVIDENCE_CHECKLIST),
    }


def assess_growth(record: dict[str, Any], growth_opportunity_score) -> dict[str, Any]:
    """Growth is not derivable from NDVI/NDBI, however real the imagery is.

    Observed land-cover change is real evidence of *land cover* changing. It does
    not distinguish a new warehouse from a cleared field, a seasonal crop cycle
    from construction, or any of it from investment value. Inferring an
    investment-growth score from two spectral indices would be the same
    unsupported leap the audit removed, just with better inputs.
    """
    satellite = _section(record, "satellite")
    change_type = satellite.get("change_type")
    if satellite_is_synthetic(record):
        return {
            "factor": "growth",
            "score": None,
            "status": "unavailable",
            "basis": "Growth unavailable: the satellite series is synthetic demo data, not observed imagery.",
            "limitations": "Configure an imagery provider to obtain real observations.",
            "checklist": ["Observed multi-date satellite imagery for this polygon"],
        }
    if (satellite.get("collection") or {}).get("status") == "timed_out":
        return {
            "factor": "growth",
            "score": None,
            "status": "unavailable",
            "basis": "Satellite collection timed out before the evidence deadline, so no land-cover series is in this report.",
            "limitations": "Analyse the same boundary again: scenes already read are cached and reused.",
            "checklist": list(GROWTH_EVIDENCE_CHECKLIST),
        }
    if change_type in (None, "insufficient_evidence"):
        return {
            "factor": "growth",
            "score": None,
            "status": "unavailable",
            "basis": "Growth unavailable: no usable satellite observations for this parcel and date range.",
            "limitations": "At least two cloud-free observations are required.",
            "checklist": ["Two or more usable observations inside the analysis window"],
        }
    if not satellite.get("change_method"):
        # statistical_change_v1 (snapshots before 2026-10-12): one straight line through every date.
        observed = (f"'{change_type.replace('_', ' ')}' under the superseded v1 trend method, which did not "
                    "compare like seasons and filed unclear movement under no change")
    else:
        observed = None
    observed = observed or {
        "no_change": "no material land-cover change between same-season images",
        "inconclusive": "an inconclusive land-cover change signal",
        "construction_growth": "land-cover change consistent with construction",
        "vegetation_loss": "vegetation loss",
        "vegetation_gain": "vegetation gain",
    }.get(change_type, change_type.replace("_", " "))
    return {
        "factor": "growth",
        "score": None,
        "status": "not_integrated",
        "basis": (
            f"Satellite imagery shows {observed}. That is land cover, reported separately; no investment-growth "
            "score is derived from it."
        ),
        "limitations": (
            "NDVI/NDBI measure vegetation and built-up reflectance. They cannot separate construction "
            "from seasonal cropping or clearance, and say nothing about prices, demand, planning "
            "approvals or infrastructure investment. A growth score needs economic evidence, not "
            "spectral indices."
        ),
        "checklist": list(GROWTH_EVIDENCE_CHECKLIST),
    }


def _metres(value: Any) -> str:
    return f"{value:,.0f} m" if isinstance(value, (int, float)) else "not found"


def assess_accessibility(
    record: dict[str, Any],
    evaluation: dict[str, Any],
    accessibility_components,
) -> dict[str, Any]:
    """Proximity from OpenStreetMap under the user's distance limits, flagged as straight-line."""
    infrastructure = _section(record, "infrastructure")
    if infrastructure.get("nearest_road_distance_m") is None and infrastructure.get("nearest_school_distance_m") is None             and infrastructure.get("search_radius_m") is None:
        return {
            "factor": "accessibility",
            "score": None,
            "status": "unavailable",
            "basis": "Accessibility unavailable: no infrastructure was retrieved for this parcel.",
            "limitations": "The OpenStreetMap lookup returned nothing usable, or failed.",
            "checklist": ["Regional OpenStreetMap data covering this parcel"],
            "details": None,
        }
    parts = accessibility_components({**record, "evaluation": evaluation}, _section(evaluation, "preferences"))

    def describe(name: str, part: dict[str, Any]) -> str:
        if part["distance_m"] is None:
            return (f"{name}: {part['measured_from']}, so it scores 0 against your {part['cap_m']:,.0f} m limit"
                    if part["sub_score"] is not None else f"{name}: not found, so it is left out")
        centroid = (f" ({_metres(part['centroid_distance_m'])} from the centroid)"
                    if part["measured_from"] == "parcel boundary" and part["centroid_distance_m"] is not None else "")
        return (f"{name} {_metres(part['distance_m'])} from the {part['measured_from']}{centroid}: "
                f"{part['sub_score']:.0f}/100 against your {part['cap_m']:,.0f} m limit")

    return {
        "factor": "accessibility",
        "score": parts["score"],
        "status": "indicative" if parts["score"] is not None else "unavailable",
        "basis": (
            f"{describe('Nearest mapped road', parts['road'])}; {describe('nearest mapped school', parts['school'])}. "
            f"Weighted road x{parts['road']['weight']:g}, school x{parts['school']['weight']:g} "
            "(property type and your importance settings). A sub-score falls linearly to 0 at your limit."
        ),
        "limitations": (
            "Straight-line distances to OpenStreetMap geometry, not routed travel distances. A nearby road is not "
            "proof of legal or physical access, and OpenStreetMap can miss schools. The drawn boundary is not a "
            "cadastral boundary."
        ),
        "checklist": [] if parts["score"] is not None else ["Regional OpenStreetMap data covering this parcel"],
        "details": parts,
    }
