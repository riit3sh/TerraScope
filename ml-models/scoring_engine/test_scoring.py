from scoring_engine.scoring import (
    accessibility_score,
    compute_evaluation,
    evaluate_sensitivity,
    get_default_profile,
    legal_risk_score,
)


def parcel(**overrides):
    record = {
        "land_records": {"title_clear": True, "encumbrance_flag": False},
        "rera": {"is_rera_project": True},
        "satellite": {"change_type": "construction_growth", "change_confidence": 0.95},
        "infrastructure": {
            "nearest_road_distance_m": 200,
            "nearest_road_type": "primary",
            "nearest_school_distance_m": 300,
        },
        "risk": {"flood_risk_score": 10},
        "opportunity": {"growth_score": 85},
        "location": {"district": "Pune"},
        "geometry": {"type": "Polygon"},
    }
    record.update(overrides)
    return record


def test_clean_high_growth_parcel_is_buy_with_high_explainable_scores():
    result = compute_evaluation(parcel(), get_default_profile("investor"))
    assert result["recommendation"] == "BUY"
    assert result["growth_score"] > 90
    assert sum(item["contribution"] for item in result["weighted_contributions"]) == result["composite_score"]
    assert "composite" in result["reasoning_summary"] and "growth" in result["reasoning_summary"]


def test_flood_prone_parcel_passes_through_risk_as_low_flood_safety():
    safe = compute_evaluation(parcel(), get_default_profile("conservative"))
    flood_prone = compute_evaluation(parcel(risk={"flood_risk_score": 95}), get_default_profile("conservative"))
    assert flood_prone["flood_safety_score"] == 5
    assert flood_prone["composite_score"] < safe["composite_score"]


def test_encumbered_title_triggers_hard_avoid():
    record = parcel(land_records={"title_clear": False, "encumbrance_flag": True}, rera={"is_rera_project": False})
    result = compute_evaluation(record, get_default_profile("developer"))
    assert legal_risk_score({**record, "evaluation": get_default_profile("developer")}) >= 90
    assert result["recommendation"] == "AVOID"


def test_strict_rera_penalty_is_stronger_than_informational():
    record = parcel(rera={"is_rera_project": False})
    strict = compute_evaluation(record, get_default_profile("developer"))
    informational = compute_evaluation(record, get_default_profile("homebuyer"))
    assert strict["legal_safety_score"] < informational["legal_safety_score"]


def test_property_type_changes_accessibility_importance():
    distances = {"nearest_road_distance_m": 100, "nearest_school_distance_m": 4500}
    residential = accessibility_score(parcel(infrastructure=distances, evaluation={"property_type": "residential"}), {})
    industrial = accessibility_score(parcel(infrastructure=distances, evaluation={"property_type": "industrial"}), {})
    assert industrial > residential


def test_custom_weights_are_normalized_and_visible_in_contributions():
    evaluation = get_default_profile("custom")
    evaluation["weights"] = {"growth_pct": 9, "legal_safety_pct": 1, "accessibility_pct": 0, "flood_safety_pct": 0}
    result = compute_evaluation(parcel(), evaluation)
    weights = {item["factor"]: item["contribution"] for item in result["weighted_contributions"]}
    assert abs(result["composite_score"] - sum(weights.values())) < 0.01
    assert weights["growth"] > weights["legal_safety"]


def test_identical_evidence_can_produce_profile_specific_results():
    record = parcel(infrastructure={"nearest_road_distance_m": 200, "nearest_school_distance_m": 4500})
    homebuyer = compute_evaluation(record, get_default_profile("homebuyer"))
    investor = compute_evaluation(record, get_default_profile("investor"))
    assert homebuyer["accessibility_score"] != investor["accessibility_score"]
    assert homebuyer["composite_score"] != investor["composite_score"]


def test_missing_data_reduces_confidence():
    complete = compute_evaluation(parcel(), get_default_profile("conservative"))
    incomplete = compute_evaluation(
        {"risk": {"flood_risk_score": None}, "satellite": {"change_type": "insufficient_evidence"}},
        get_default_profile("conservative"),
    )
    assert incomplete["confidence"] < complete["confidence"]


def test_sensitivity_reports_changed_factors_and_magnitude():
    baseline = get_default_profile("homebuyer")
    changed = get_default_profile("investor")
    result = evaluate_sensitivity(parcel(), baseline, changed)
    assert result["factors"]
    assert all({"factor", "baseline", "changed", "delta"} <= set(item) for item in result["factors"])

