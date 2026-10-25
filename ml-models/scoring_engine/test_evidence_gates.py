"""Regression tests for the evidence audit.

Each test pins a way the engine previously turned absent evidence into a
confident-looking number.
"""

from __future__ import annotations

import copy

from scoring_engine.scoring import compute_evaluation


EVALUATION = {
    "profile": "custom",
    "property_type": "commercial",
    "investment_horizon": "under_1y",
    "weights": {"growth_pct": 29.0, "legal_safety_pct": 38.0, "accessibility_pct": 5.0, "flood_safety_pct": 28.0},
    "preferences": {"road_importance": "medium", "school_importance": "high", "rera_requirement": "important"},
}

# The real Kadapa parcel, snapshot 63188e21: no land records, no flood data,
# synthetic satellite, real OSM infrastructure.
KADAPA = {
    "parcel_id": "ee0047a6-35fd-4520-a275-8b9464214832",
    "location": {"latitude": 14.4511446, "longitude": 78.8445324,
                 "address": "Kadapa, YSR Kadapa, Andhra Pradesh, 516001, India",
                 "village": None, "district": None, "state": None, "pincode": None},
    "land_records": None,
    "rera": {"is_rera_project": None, "rera_registration_number": None, "promoter_name": None,
             "registered_completion_date": None, "source_url": None},
    "satellite": {"change_detected": False, "change_type": "no_change", "change_confidence": 0.385},
    "infrastructure": {"nearest_road_distance_m": 19.32, "nearest_road_type": "unclassified",
                       "nearest_school_distance_m": 2100.75},
    "risk": {"flood_risk_score": None, "flood_risk_basis": None,
             "terrain_relative_elevation_score": 55, "elevation_m": 138.448883},
    "opportunity": None,
    "evidence": [
        {"source_type": "satellite", "source_reference": "SYNTHETIC demo series (no AppEEARS credentials)",
         "freshness": "seed_data", "title": "SYNTHETIC demo satellite series"},
        {"source_type": "openstreetmap", "source_reference": "Overpass API", "freshness": "live"},
    ],
}


def _with(**changes):
    record = copy.deepcopy(KADAPA)
    record.update(changes)
    return record


# --- missing land records --------------------------------------------------

def test_missing_land_records_yield_no_legal_score() -> None:
    """Absence of records is not evidence of clear title, and not a number."""
    result = compute_evaluation(KADAPA, EVALUATION)
    assert result["legal_safety_score"] is None
    legal = next(f for f in result["factors"] if f["factor"] == "legal_safety")
    assert legal["status"] == "unavailable"
    assert "not evidence of clear title" in legal["basis"]
    assert len(legal["checklist"]) >= 4


def test_uploaded_text_does_not_establish_title() -> None:
    """A user upload in the ledger must not unlock a legal score."""
    record = _with(evidence=KADAPA["evidence"] + [
        {"source_type": "user_upload", "source_reference": "title.txt", "freshness": "user_upload"},
    ])
    assert compute_evaluation(record, EVALUATION)["legal_safety_score"] is None


def test_unrelated_state_rera_match_does_not_establish_title() -> None:
    """A Maharashtra registration cannot verify an Andhra Pradesh parcel."""
    record = _with(rera={"is_rera_project": True, "rera_registration_number": "P52100012345",
                         "promoter_name": "Some Pune Developer", "registered_completion_date": None,
                         "source_url": None})
    result = compute_evaluation(record, EVALUATION)
    assert result["legal_safety_score"] is None, "a RERA hit is not an ownership record"


# --- flood -----------------------------------------------------------------

def test_elevation_only_input_yields_no_flood_score() -> None:
    """One elevation point against a baseline is not a flood assessment."""
    result = compute_evaluation(KADAPA, EVALUATION)
    assert result["flood_safety_score"] is None
    flood = next(f for f in result["factors"] if f["factor"] == "flood_safety")
    assert flood["status"] == "unavailable"
    for term in ("Coastal", "fluvial", "pluvial"):
        assert term in flood["limitations"]
    assert "inland does not establish safety" in flood["limitations"]


def test_terrain_position_score_is_not_a_flood_headline() -> None:
    """The unexplained 0-100 terrain figure must not appear as flood safety."""
    flood = next(f for f in compute_evaluation(KADAPA, EVALUATION)["factors"] if f["factor"] == "flood_safety")
    assert "/100" not in flood["basis"]
    assert flood["score"] is None


def _component(mechanism, status, summary="evidence"):
    return {"mechanism": mechanism, "status": status, "source": None, "period": None,
            "resolution": None, "coverage_share": None, "summary": summary}


def test_flood_evidence_gives_a_partial_assessment_without_a_score() -> None:
    record = _with(flood_indicators={"assessment_status": "partial", "components": [
        _component("river_flooding", "assessed", "Modelled river inundation first reaches the parcel in the 1-in-20-year scenario."),
        _component("historical_inundation", "not_integrated"),
        _component("rainfall_waterlogging", "not_assessed"),
        _component("coastal_flooding", "not_assessed"),
    ]})
    result = compute_evaluation(record, EVALUATION)
    flood = next(f for f in result["factors"] if f["factor"] == "flood_safety")
    assert flood["status"] == "partial"
    assert flood["score"] is None and result["flood_safety_score"] is None
    assert flood["basis"].startswith("River flood exposure assessed")
    assert "other mechanisms incomplete" in flood["basis"]
    assert "rainfall waterlogging" in flood["basis"] and "coastal flooding" in flood["basis"]
    # The checklist names what is missing, not the river map that was just used.
    assert not any("hazard map" in item for item in flood["checklist"])
    assert any("Rainfall" in item for item in flood["checklist"])
    # A withheld factor carrying weight still withholds the verdict.
    assert result["recommendation"] == "INSUFFICIENT_EVIDENCE"
    # Every factor status must be one the shared schema accepts (the service validates it).
    import json
    from pathlib import Path

    schema = json.loads((Path(__file__).resolve().parents[2] / "docs" / "schema" / "parcel_schema.json").read_text(encoding="utf-8"))
    allowed = schema["properties"]["score_breakdown"]["properties"]["factors"]["items"]["properties"]["status"]["enum"]
    assert {factor["status"] for factor in result["factors"]} <= set(allowed)


def test_only_missing_flood_evidence_never_becomes_safe() -> None:
    """No usable component: unavailable and unscored - never 100, never 'safe'."""
    record = _with(flood_indicators={"assessment_status": "unavailable", "components": [
        _component("river_flooding", "unavailable", "River flood hazard not assessed: provider timeout."),
        _component("rainfall_waterlogging", "not_assessed"),
    ]})
    flood = next(f for f in compute_evaluation(record, EVALUATION)["factors"] if f["factor"] == "flood_safety")
    assert flood["status"] == "unavailable"
    assert flood["score"] is None
    assert "unknown, not safe" in flood["limitations"]


# --- growth ----------------------------------------------------------------

def test_snapshot_without_area_history_yields_no_growth_score() -> None:
    """Snapshots made before the area history was collected say how to get it."""
    result = compute_evaluation(KADAPA, EVALUATION)
    assert result["growth_score"] is None
    growth = next(f for f in result["factors"] if f["factor"] == "growth")
    assert growth["status"] == "unavailable" and "Analyse the same boundary again" in growth["basis"]


def test_provider_failure_yields_no_growth_score() -> None:
    record = _with(satellite={"change_type": "insufficient_evidence", "change_detected": None,
                              "change_confidence": None},
                   evidence=[{"source_type": "openstreetmap", "freshness": "live"}])
    assert compute_evaluation(record, EVALUATION)["growth_score"] is None


def test_real_observed_change_still_yields_no_growth_score() -> None:
    """Real imagery measures land cover, which is not investment growth."""
    record = _with(
        satellite={"change_type": "construction_growth", "change_detected": True, "change_confidence": None,
                   "change_method": {"method": "seasonal_pairs_v2"}},
        evidence=[{"source_type": "satellite",
                   "source_reference": "Sentinel-2 L2A (Microsoft Planetary Computer)",
                   "freshness": "live"}],
    )
    result = compute_evaluation(record, EVALUATION)
    assert result["growth_score"] is None
    growth = next(f for f in result["factors"] if f["factor"] == "growth")
    assert "construction" not in growth["basis"], "the plot's own NDVI change is not area growth"


# --- accessibility ---------------------------------------------------------

def test_accessibility_is_marked_straight_line_not_road_network() -> None:
    access = next(f for f in compute_evaluation(KADAPA, EVALUATION)["factors"] if f["factor"] == "accessibility")
    assert access["status"] == "indicative"
    assert "not routed travel distances" in access["limitations"]
    assert "not proof of legal or physical access" in access["limitations"]
    assert "not proof of legal or physical access" in access["limitations"]


def test_provider_failure_yields_no_accessibility_score() -> None:
    record = _with(infrastructure={"nearest_road_distance_m": None, "nearest_road_type": None,
                                   "nearest_school_distance_m": None})
    assert compute_evaluation(record, EVALUATION)["accessibility_score"] is None


# --- recommendation --------------------------------------------------------

def test_recommendation_is_withheld_when_weighted_evidence_is_missing() -> None:
    result = compute_evaluation(KADAPA, EVALUATION)
    assert result["recommendation"] == "INSUFFICIENT_EVIDENCE"
    assert result["composite_score"] is None
    assert set(result["unassessed_factors"]) == {"legal_safety", "flood_safety", "growth"}
    assert result["assessed_weight_pct"] == 5.0


def test_missing_factors_are_not_renormalised_into_a_better_result() -> None:
    """The old engine scored the same parcel WAIT at composite 50.9."""
    result = compute_evaluation(KADAPA, EVALUATION)
    assert result["composite_score"] is None
    contributions = {c["factor"] for c in result["weighted_contributions"]}
    assert contributions == {"accessibility"}, "only evidenced factors may contribute"


def test_zero_weight_on_a_missing_factor_does_not_block() -> None:
    """A factor the user gave no weight cannot veto the verdict."""
    evaluation = copy.deepcopy(EVALUATION)
    evaluation["weights"] = {"growth_pct": 0.0, "legal_safety_pct": 0.0,
                             "accessibility_pct": 100.0, "flood_safety_pct": 0.0}
    result = compute_evaluation(KADAPA, evaluation)
    assert result["unassessed_factors"] == []
    assert result["recommendation"] in {"BUY", "WAIT", "AVOID"}
    assert result["composite_score"] is not None


def test_percentage_confidence_is_not_emitted() -> None:
    """The old figure was not a probability of anything."""
    assert compute_evaluation(KADAPA, EVALUATION)["confidence"] is None


def test_stale_or_absent_evidence_never_becomes_fifty() -> None:
    """Nothing may silently substitute the neutral midpoint."""
    bare = {"parcel_id": "x", "location": {}, "land_records": None, "rera": None,
            "satellite": {}, "infrastructure": {}, "risk": {}, "opportunity": None, "evidence": []}
    result = compute_evaluation(bare, EVALUATION)
    for key in ("legal_safety_score", "flood_safety_score", "growth_score", "accessibility_score"):
        assert result[key] is None, f"{key} was invented from no evidence"
    assert result["recommendation"] == "INSUFFICIENT_EVIDENCE"


# --- buy / wait from the area's history ------------------------------------

def _history(first: float, last: float, slope: float, far_first: float = 0.3, plot=("crops", "crops")) -> dict:
    trend = {"first_year": 2017, "first_share": first, "last_year": 2023, "last_share": last, "years_used": 7,
             "slope_pts_per_year": slope}
    return {"status": "assessed", "trend_within_1km": trend,
            "trend_1_to_3km": {**trend, "first_share": far_first, "last_share": far_first},
            "parcel": [{"year": 2017, "dominant": plot[0]}, {"year": 2023, "dominant": plot[1]}]}


def _decide(history: dict, **changes):
    evaluation = copy.deepcopy(EVALUATION)
    evaluation["weights"] = {"growth_pct": 50.0, "legal_safety_pct": 25.0, "accessibility_pct": 25.0, "flood_safety_pct": 0.0}
    return compute_evaluation(_with(land_cover_history=history, **changes), evaluation)


def test_fast_development_around_the_plot_is_a_buy_with_title_checks() -> None:
    result = _decide(_history(0.63, 0.73, 1.92))
    assert result["growth_score"] == 96.0
    assert result["recommendation"] == "BUY"
    assert "63.0% (2017) to 73.0% (2023) built within 1 km, trend +1.9 points a year" in result["reasoning_summary"]
    assert any("Ownership record" in check for check in result["pre_purchase_checks"]), "legal is a check, never verified"
    assert result["legal_safety_score"] is None


def test_little_development_is_a_wait_that_names_what_holds_it_back() -> None:
    result = _decide(_history(0.01, 0.02, 0.11))
    assert result["recommendation"] == "WAIT"
    assert "Holding it back: area growth" in result["reasoning_summary"]


def test_built_out_area_does_not_block_and_is_not_scored() -> None:
    result = _decide(_history(1.0, 1.0, 0.0, far_first=0.97))
    growth = next(f for f in result["factors"] if f["factor"] == "growth")
    assert growth["status"] == "established" and growth["score"] is None
    assert result["recommendation"] in {"BUY", "WAIT"}
    assert {c["factor"] for c in result["weighted_contributions"]} == {"accessibility"}


def test_frequent_river_flooding_is_a_red_flag_whatever_the_growth() -> None:
    flood = {"river_flood": {"scenarios": [{"return_period_years": 10, "flooded_share_of_parcel": 0.0},
                                           {"return_period_years": 50, "flooded_share_of_parcel": 0.6}]}}
    result = _decide(_history(0.63, 0.73, 1.92), flood_indicators=flood)
    assert result["recommendation"] == "AVOID"
    assert "60% of the plot in the 1-in-50-year flood" in result["red_flags"][0]


def test_a_likely_water_bed_is_a_red_flag() -> None:
    flood = {"surface_water": {"parcel": {"occurrence_mean_pct": 35.0}}}
    assert _decide(_history(0.63, 0.73, 1.92), flood_indicators=flood)["recommendation"] == "AVOID"
    wet_plot = _history(0.63, 0.73, 1.92, plot=("water", "crops"))
    assert "water or flooded vegetation in 2017" in _decide(wet_plot)["red_flags"][0]


def test_a_change_on_the_plot_itself_becomes_a_check() -> None:
    result = _decide(_history(0.63, 0.73, 1.92, plot=("crops", "built")))
    assert any("changed from crops (2017) to built area (2023)" in c for c in result["pre_purchase_checks"])


def test_a_flat_trend_never_prints_as_minus_zero_and_a_dense_area_is_not_called_empty() -> None:
    """Regression (Vijayawada, 2026-10-25): 88.2% -> 88.6% built read "88% to 89% (-0.0 points a year)" under
    "Little or no development". The all-years fit was float noise (~-3e-15) rounded to -0.0."""
    result = _decide(_history(0.8822, 0.8858, -0.0, far_first=0.80))
    growth = next(f for f in result["factors"] if f["factor"] == "growth")
    assert "-0.0" not in growth["basis"]
    assert "was 88.2% in 2017 and 88.6% in 2023; the trend across all 7 years is 0.0 points a year" in growth["basis"]
    assert growth["basis"].startswith("Established, densely built area")
    # Level is not rate: an established area is neither scored nor penalised; the decision rests on access.
    assert growth["status"] == "established" and growth["score"] is None
    assert {c["factor"] for c in result["weighted_contributions"]} == {"accessibility"}


def test_missing_regional_data_names_the_exact_install_command() -> None:
    """Regression (Vijayawada, 2026-10-25): the report said only "no infrastructure was retrieved"."""
    record = _with(
        infrastructure={},
        location={"state": "Andhra Pradesh"},
        evidence=[{"source_type": "openstreetmap", "summary": "OpenStreetMap infrastructure is unavailable for this "
                   "parcel: No regional OpenStreetMap data is installed for Andhra Pradesh. Install it with: "
                   "terrascope.cmd fetch-data andhra-pradesh The Overpass fallback is off."}],
    )
    result = compute_evaluation(record, EVALUATION)
    access = next(f for f in result["factors"] if f["factor"] == "accessibility")
    assert access["score"] is None and "terrascope.cmd fetch-data andhra-pradesh" in access["basis"]
    assert "Andhra Pradesh" in access["basis"]


def test_a_dense_area_that_is_still_building_fast_is_scored_not_exempted() -> None:
    result = _decide(_history(0.80, 0.92, 2.0, far_first=0.6))
    growth = next(f for f in result["factors"] if f["factor"] == "growth")
    assert growth["status"] == "indicative" and growth["score"] == 100.0


def test_decisions_use_buyer_words_walk_away_and_insufficient_data() -> None:
    flood = {"river_flood": {"scenarios": [{"return_period_years": 20, "flooded_share_of_parcel": 0.5}]}}
    walk = _decide(_history(0.63, 0.73, 1.92), flood_indicators=flood)
    assert walk["recommendation"] == "AVOID" and walk["reasoning_summary"].startswith("WALK AWAY:")
    unknown = _decide({}, infrastructure={})  # no area history and no infrastructure
    assert unknown["recommendation"] == "INSUFFICIENT_EVIDENCE"
    assert unknown["reasoning_summary"].startswith("INSUFFICIENT DATA:")


def test_wait_names_what_holds_it_back_and_buy_lists_unverified_legal_checks() -> None:
    wait = _decide(_history(0.01, 0.02, 0.11))
    assert wait["reasoning_summary"].startswith("WAIT: there is potential")
    assert "Holding it back: area growth 6 of 100" in wait["reasoning_summary"]
    buy = _decide(_history(0.63, 0.73, 1.92))
    assert "Title, encumbrance, approvals and RERA are not verified" in buy["reasoning_summary"]
