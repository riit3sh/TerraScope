"""Evidence gates for TerraScope scoring.

A score is only emitted when evidence actually supports it. Missing evidence
stays unknown: it is never substituted with 50, and it is never silently dropped
so that the surviving factors renormalise into a better-looking result.
"""

from __future__ import annotations

from typing import Any


LEGAL_EVIDENCE_CHECKLIST = (
    "Ownership record matched to this survey / subdivision number",
    "Encumbrance certificate or registered transaction history",
    "Land-use zoning approval or restriction record",
    "Project registration from the parcel's own state authority",
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
        state = _section(record, "location").get("state") or "this parcel's state"
        return {
            "factor": "legal_safety",
            "score": None,
            "status": "unavailable",
            "basis": (
                "Legal verification incomplete: no authoritative land record was retrieved or "
                f"matched for this parcel ({state}). Absence of records is not evidence of clear title."
            ),
            "limitations": (
                "No ownership, encumbrance, restriction or land-use approval source is integrated. "
                "The only registration dataset present is a MahaRERA seed, which covers Maharashtra "
                "and cannot speak to a parcel in another state."
            ),
            "checklist": list(LEGAL_EVIDENCE_CHECKLIST),
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
        basis = "Partial flood assessment available. "
        if river.get("status") in ("assessed", "partial"):
            basis += f"River flooding (modelled): {river.get('summary')} "
        else:
            basis += f"River flooding: {river.get('summary') or 'not assessed.'} "
        basis += "Assessed: " + ", ".join(c["mechanism"].replace("_", " ") for c in usable) + "."
        if missing:
            basis += " Not assessed: " + ", ".join(missing) + "."
        return {
            "factor": "flood_safety",
            "score": None,
            "status": "partial",
            "basis": basis[:900],
            "limitations": (
                "No overall Flood Safety score: no method combining river, rainfall, coastal and terrain evidence "
                "has been independently validated, and unassessed mechanisms are unknown, not safe. River hazard "
                "maps are modelled scenarios at ~90 m for rivers with basins over ~500 km2, not observed floods "
                "and not building-level safety. Surface water seen by Landsat is not flood history, and height "
                "above the nearest mapped water is a terrain indicator, not HAND or a flood probability."
            ),
            "checklist": list(FLOOD_EVIDENCE_CHECKLIST),
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
    if change_type in (None, "insufficient_evidence"):
        return {
            "factor": "growth",
            "score": None,
            "status": "unavailable",
            "basis": "Growth unavailable: no usable satellite observations for this parcel and date range.",
            "limitations": "At least two cloud-free observations are required.",
            "checklist": ["Two or more usable observations inside the analysis window"],
        }
    return {
        "factor": "growth",
        "score": None,
        "status": "not_integrated",
        "basis": (
            f"Observed land-cover change for this parcel is classified as {change_type.replace('_', ' ')}, "
            "which is reported as evidence in its own right. No investment-growth score is derived from it."
        ),
        "limitations": (
            "NDVI/NDBI measure vegetation and built-up reflectance. They cannot separate construction "
            "from seasonal cropping or clearance, and say nothing about prices, demand, planning "
            "approvals or infrastructure investment. A growth score needs economic evidence, not "
            "spectral indices."
        ),
        "checklist": [
            "Registered transaction volumes or price trend for the locality",
            "Approved layouts, building permissions or master-plan land-use change",
            "Committed infrastructure projects with dates and distances",
        ],
    }


def assess_accessibility(
    record: dict[str, Any],
    evaluation: dict[str, Any],
    accessibility_score,
) -> dict[str, Any]:
    """Accessibility from OpenStreetMap, flagged as straight-line."""
    infrastructure = _section(record, "infrastructure")
    road = infrastructure.get("nearest_road_distance_m")
    school = infrastructure.get("nearest_school_distance_m")
    if road is None and school is None:
        return {
            "factor": "accessibility",
            "score": None,
            "status": "unavailable",
            "basis": "Accessibility unavailable: no infrastructure was retrieved for this parcel.",
            "limitations": "The OpenStreetMap lookup returned nothing usable, or failed.",
            "checklist": ["A successful Overpass query covering this parcel"],
        }
    return {
        "factor": "accessibility",
        "score": accessibility_score({**record, "evaluation": evaluation}, _section(evaluation, "preferences")),
        "status": "indicative",
        "basis": (
            "Straight-line distance from the polygon centroid to the nearest OpenStreetMap "
            f"road ({road} m) and school ({school} m)."
        ),
        "limitations": (
            "These are straight-line (haversine) distances, NOT road-network travel distances, and a "
            "nearby way is not proof of legal or physical access. The distance caps are fixed constants; "
            "the max_road_distance_m and max_school_distance_m preferences are accepted but not applied."
        ),
        "checklist": [],
    }
