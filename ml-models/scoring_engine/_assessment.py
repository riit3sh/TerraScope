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
    """Flood safety only when a real flood source populated risk.flood_risk_score.

    No flood hazard dataset is integrated today, so the ETL leaves that field
    null and this returns unavailable. The scored branch exists so that wiring a
    genuine hazard source in later does not require touching the verdict logic;
    the terrain indicator must never populate it.
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
    indicator = risk.get("terrain_relative_elevation_score")
    note = (
        f" A relative terrain indicator ({indicator}/100) is reported separately."
        if isinstance(indicator, (int, float))
        else ""
    )
    return {
        "factor": "flood_safety",
        "score": None,
        "status": "unavailable",
        "basis": "Flood assessment unavailable: no flood hazard evidence is integrated for this parcel." + note,
        "limitations": (
            "Coastal, fluvial (river) and pluvial (rainfall/drainage) flooding are distinct and none is "
            "assessed. No flood hazard or inundation map, historical flood extent, watercourse distance, "
            "drainage network or rainfall record is used. Being inland does not establish safety, and "
            "district flood history would not establish risk for this individual plot."
        ),
        "checklist": list(FLOOD_EVIDENCE_CHECKLIST),
    }


def assess_growth(record: dict[str, Any], growth_opportunity_score) -> dict[str, Any]:
    """Growth needs real observed change; a synthetic series cannot support it."""
    change_type = _section(record, "satellite").get("change_type")
    if satellite_is_synthetic(record):
        return {
            "factor": "growth",
            "score": None,
            "status": "unavailable",
            "basis": "Growth unavailable: the satellite series is synthetic demo data, not observed imagery.",
            "limitations": "Configure AppEEARS credentials to obtain real NDVI/NDBI observations.",
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
        "score": growth_opportunity_score({**record, "evaluation": {}}),
        "status": "assessed",
        "basis": f"Derived from observed satellite change classified as {change_type}.",
        "limitations": "Built-up change is a proxy for growth, moderated by the nearest road category.",
        "checklist": [],
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
