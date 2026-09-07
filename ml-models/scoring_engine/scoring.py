"""Explainable, weighted rule-based scoring for TerraScope evaluations."""

from __future__ import annotations

from copy import deepcopy
from typing import Any


# Every tunable scoring value lives here so Review 2 behavior is easy to audit.
LEGAL_TITLE_NOT_CLEAR_PENALTY = 40
LEGAL_ENCUMBRANCE_PENALTY = 30
LEGAL_MISSING_RERA_PENALTY = 20
LEGAL_MISSING_LAND_RECORDS_PENALTY = 10
HARD_LEGAL_RISK_THRESHOLD = 70
BUY_COMPOSITE_THRESHOLD = 75
WAIT_COMPOSITE_THRESHOLD = 50
MAX_USEFUL_ROAD_DISTANCE_M = 3_000.0
MAX_USEFUL_SCHOOL_DISTANCE_M = 5_000.0
DEFAULT_ROAD_IMPORTANCE = 1.0
DEFAULT_SCHOOL_IMPORTANCE = 1.0
PROPERTY_IMPORTANCE = {
    "residential": {"road": 1.0, "school": 1.5},
    "commercial": {"road": 1.5, "school": 0.7},
    "industrial": {"road": 1.7, "school": 0.5},
    "mixed_use": {"road": 1.3, "school": 1.2},
}
IMPORTANCE_MULTIPLIERS = {"low": 0.7, "medium": 1.0, "high": 1.4}
RERA_PENALTIES = {"strict": 35, "important": 20, "informational": 5}
ROAD_GROWTH_MODIFIERS = {
    "motorway": 1.10,
    "trunk": 1.10,
    "primary": 1.08,
    "secondary": 1.04,
    "tertiary": 1.0,
    "residential": 0.96,
    "service": 0.92,
    "track": 0.85,
    "path": 0.85,
}


def _section(record: dict[str, Any], name: str) -> dict[str, Any]:
    value = record.get(name)
    return value if isinstance(value, dict) else {}


def _evaluation_property_type(record: dict[str, Any]) -> str:
    evaluation = _section(record, "evaluation")
    return str(evaluation.get("property_type") or record.get("property_type") or "residential").lower()


def _is_development_context(record: dict[str, Any]) -> bool:
    property_type = _evaluation_property_type(record)
    evaluation = _section(record, "evaluation")
    profile = str(evaluation.get("profile") or record.get("profile") or "").lower()
    return property_type in {"commercial", "industrial", "mixed_use"} or profile == "developer"


def legal_risk_score(record: dict[str, Any]) -> float:
    """Return legal risk from 0 (low) to 100 (high), with each penalty visible."""
    land_records = record.get("land_records")
    rera = record.get("rera")
    risk = 0
    if isinstance(land_records, dict):
        if land_records.get("title_clear") is False:
            risk += LEGAL_TITLE_NOT_CLEAR_PENALTY
        if land_records.get("encumbrance_flag") is True:
            risk += LEGAL_ENCUMBRANCE_PENALTY
    else:
        risk += LEGAL_MISSING_LAND_RECORDS_PENALTY
    if _is_development_context(record) and (not isinstance(rera, dict) or rera.get("is_rera_project") is not True):
        risk += LEGAL_MISSING_RERA_PENALTY
    return float(min(100, risk))


def _distance_score(distance: Any, max_useful_distance: float) -> float | None:
    if not isinstance(distance, (int, float)):
        return None
    return max(0.0, min(100.0, 100.0 * (1.0 - float(distance) / max_useful_distance)))


def accessibility_score(record: dict[str, Any], preferences: dict[str, Any] | None) -> float:
    """Score proximity, using property-aware defaults and explicit preferences."""
    preferences = preferences or {}
    infrastructure = _section(record, "infrastructure")
    property_weights = PROPERTY_IMPORTANCE.get(_evaluation_property_type(record), {
        "road": DEFAULT_ROAD_IMPORTANCE,
        "school": DEFAULT_SCHOOL_IMPORTANCE,
    })
    road_importance = property_weights["road"] * IMPORTANCE_MULTIPLIERS.get(preferences.get("road_importance"), 1.0)
    school_importance = property_weights["school"] * IMPORTANCE_MULTIPLIERS.get(preferences.get("school_importance"), 1.0)
    road_score = _distance_score(infrastructure.get("nearest_road_distance_m"), MAX_USEFUL_ROAD_DISTANCE_M)
    school_score = _distance_score(infrastructure.get("nearest_school_distance_m"), MAX_USEFUL_SCHOOL_DISTANCE_M)
    weighted = [(road_score, road_importance), (school_score, school_importance)]
    available = [(score, weight) for score, weight in weighted if score is not None]
    if not available:
        return 50.0
    return round(sum(score * weight for score, weight in available) / sum(weight for _, weight in available), 2)


def flood_and_terrain_risk_score(record: dict[str, Any]) -> float | None:
    """Pass through Track 1's flood-risk proxy, where available."""
    value = _section(record, "risk").get("flood_risk_score")
    return float(value) if isinstance(value, (int, float)) else None


def growth_opportunity_score(record: dict[str, Any]) -> float:
    """Score growth evidence, moderated by the nearest road category."""
    opportunity = _section(record, "opportunity")
    satellite = _section(record, "satellite")
    base = float(opportunity.get("growth_score", 50)) if isinstance(opportunity.get("growth_score", 50), (int, float)) else 50.0
    change_type = satellite.get("change_type")
    confidence = float(satellite.get("change_confidence", 0) or 0)
    if change_type == "construction_growth":
        base += 35.0 * max(0.0, min(1.0, confidence))
    elif change_type == "vegetation_loss":
        base -= 15.0 * max(0.0, min(1.0, confidence))
    elif change_type == "no_change":
        base += 5.0
    road_type = str(_section(record, "infrastructure").get("nearest_road_type") or "").lower()
    base *= ROAD_GROWTH_MODIFIERS.get(road_type, 0.95 if road_type else 0.9)
    return round(max(0.0, min(100.0, base)), 2)


def apply_rera_requirement(record: dict[str, Any], evaluation: dict[str, Any]) -> dict[str, Any]:
    """Return the RERA signal and profile-sensitive penalty for development contexts."""
    requirement = str(_section(evaluation, "preferences").get("rera_requirement") or "informational").lower()
    rera = record.get("rera")
    applicable = _is_development_context({**record, "evaluation": evaluation})
    positive = isinstance(rera, dict) and rera.get("is_rera_project") is True
    penalty = RERA_PENALTIES.get(requirement, RERA_PENALTIES["informational"]) if applicable and not positive else 0
    return {
        "applicable": applicable,
        "is_rera_project": positive if isinstance(rera, dict) else None,
        "requirement": requirement,
        "penalty": penalty,
    }


def _normalized_weights(evaluation: dict[str, Any]) -> dict[str, float]:
    defaults = {"growth_pct": 25.0, "legal_safety_pct": 25.0, "accessibility_pct": 25.0, "flood_safety_pct": 25.0}
    supplied = _section(evaluation, "weights")
    raw = {key: max(0.0, float(supplied.get(key, default) or 0.0)) for key, default in defaults.items()}
    total = sum(raw.values())
    if total <= 0:
        return defaults
    return {key: round(value * 100.0 / total, 4) for key, value in raw.items()}


def _data_confidence(record: dict[str, Any]) -> float:
    sections = ["location", "geometry", "land_records", "rera", "satellite", "infrastructure", "risk", "opportunity"]
    present = sum(record.get(section) not in (None, {}) for section in sections)
    satellite = _section(record, "satellite")
    if satellite.get("change_type") == "insufficient_evidence":
        present -= 0.5
    return max(0.0, min(1.0, present / len(sections)))


def _reasoning_summary(scores: dict[str, float], legal_risk: float, composite: float, recommendation: str, rera_penalty: float) -> str:
    return (
        f"{recommendation}: composite {composite:.1f}; legal risk {legal_risk:.1f} "
        f"(legal safety {scores['legal_safety_score']:.1f}); accessibility {scores['accessibility_score']:.1f}; "
        f"growth {scores['growth_score']:.1f}; flood safety {scores['flood_safety_score']:.1f}; "
        f"RERA penalty {rera_penalty:.1f}."
    )[:500]


def compute_verdict(record: dict[str, Any], evaluation: dict[str, Any]) -> dict[str, Any]:
    """Apply the hard legal-risk override, then threshold the weighted composite."""
    scoring_record = {**record, "evaluation": evaluation}
    legal_risk = legal_risk_score(scoring_record)
    rera = apply_rera_requirement(record, evaluation)
    effective_legal_risk = min(100.0, legal_risk + rera["penalty"])
    scores = {
        "legal_safety_score": 100.0 - effective_legal_risk,
        "accessibility_score": accessibility_score(scoring_record, _section(evaluation, "preferences")),
        "flood_safety_score": 100.0 - (flood_and_terrain_risk_score(scoring_record) if flood_and_terrain_risk_score(scoring_record) is not None else 50.0),
        "growth_score": growth_opportunity_score(scoring_record),
    }
    weights = _normalized_weights(evaluation)
    contributions = [
        {"factor": key.removesuffix("_score"), "contribution": round(scores[key] * weights[f"{key.removesuffix('_score')}_pct"] / 100.0, 2)}
        for key in scores
    ]
    composite = round(sum(item["contribution"] for item in contributions), 2)
    if effective_legal_risk > HARD_LEGAL_RISK_THRESHOLD:
        recommendation = "AVOID"
    elif composite >= BUY_COMPOSITE_THRESHOLD:
        recommendation = "BUY"
    elif composite >= WAIT_COMPOSITE_THRESHOLD:
        recommendation = "WAIT"
    else:
        recommendation = "AVOID"
    confidence = round(max(0.0, min(1.0, _data_confidence(record) * (0.6 + 0.4 * abs(composite - 50.0) / 50.0))), 3)
    return {
        **scores,
        "weighted_contributions": contributions,
        "composite_score": composite,
        "recommendation": recommendation,
        "confidence": confidence,
        "reasoning_summary": _reasoning_summary(scores, effective_legal_risk, composite, recommendation, rera["penalty"]),
    }


def compute_evaluation(record: dict[str, Any], evaluation: dict[str, Any]) -> dict[str, Any]:
    """Compute a complete transparent evaluation for one fixed evidence snapshot."""
    normalized = deepcopy(evaluation)
    normalized["weights"] = {f"{key}": value for key, value in _normalized_weights(normalized).items()}
    return compute_verdict(record, normalized)


def get_default_profile(profile_name: str) -> dict[str, Any]:
    """Return a named evaluation profile with explicit weights totaling 100."""
    profiles = {
        "homebuyer": {
            "profile": "homebuyer", "property_type": "residential", "investment_horizon": "5_to_10y",
            "weights": {"growth_pct": 20, "legal_safety_pct": 30, "accessibility_pct": 30, "flood_safety_pct": 20},
            "preferences": {"road_importance": "medium", "school_importance": "high", "rera_requirement": "informational"},
        },
        "developer": {
            "profile": "developer", "property_type": "mixed_use", "investment_horizon": "3_to_5y",
            "weights": {"growth_pct": 35, "legal_safety_pct": 30, "accessibility_pct": 25, "flood_safety_pct": 10},
            "preferences": {"road_importance": "high", "school_importance": "low", "rera_requirement": "strict"},
        },
        "investor": {
            "profile": "investor", "property_type": "commercial", "investment_horizon": "3_to_5y",
            "weights": {"growth_pct": 40, "legal_safety_pct": 25, "accessibility_pct": 20, "flood_safety_pct": 15},
            "preferences": {"road_importance": "high", "school_importance": "low", "rera_requirement": "important"},
        },
        "conservative": {
            "profile": "conservative", "property_type": "residential", "investment_horizon": "5_to_10y",
            "weights": {"growth_pct": 10, "legal_safety_pct": 40, "accessibility_pct": 20, "flood_safety_pct": 30},
            "preferences": {"road_importance": "medium", "school_importance": "medium", "rera_requirement": "strict"},
        },
        "custom": {
            "profile": "custom", "property_type": "residential", "investment_horizon": "3_to_5y",
            "weights": {"growth_pct": 25, "legal_safety_pct": 25, "accessibility_pct": 25, "flood_safety_pct": 25},
            "preferences": {"road_importance": "medium", "school_importance": "medium", "rera_requirement": "informational"},
        },
    }
    try:
        return deepcopy(profiles[profile_name.lower()])
    except KeyError as error:
        raise ValueError(f"Unknown evaluation profile: {profile_name}") from error


def evaluate_sensitivity(
    record: dict[str, Any],
    baseline_evaluation: dict[str, Any],
    changed_evaluation: dict[str, Any],
) -> dict[str, Any]:
    """Explain which weighted factors changed between two profile evaluations."""
    baseline = compute_evaluation(record, baseline_evaluation)
    changed = compute_evaluation(record, changed_evaluation)
    factors = []
    for factor in ("legal_safety_score", "accessibility_score", "growth_score", "flood_safety_score"):
        baseline_value = baseline[factor]
        changed_value = changed[factor]
        delta = round(changed_value - baseline_value, 2)
        if delta:
            factors.append({"factor": factor, "baseline": baseline_value, "changed": changed_value, "delta": delta})
    return {
        "verdict_changed": baseline["recommendation"] != changed["recommendation"],
        "baseline_recommendation": baseline["recommendation"],
        "changed_recommendation": changed["recommendation"],
        "composite_delta": round(changed["composite_score"] - baseline["composite_score"], 2),
        "factors": factors,
    }
