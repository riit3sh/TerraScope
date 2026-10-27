from scoring_engine.scoring import (
    accessibility_score,
    compute_evaluation,
    compute_verdict,
    evaluate_sensitivity,
    get_default_profile,
    legal_risk_score,
)


def parcel(**overrides):
    record = {
        "land_records": {"title_clear": True, "encumbrance_flag": False, "zoning_verified": True, "approvals_verified": True},
        "rera": {"is_rera_project": True},
        "satellite": {"change_type": "construction_growth", "change_confidence": 0.95},
        "infrastructure": {
            "nearest_road_distance_m": 200,
            "nearest_road_type": "primary",
            "nearest_school_distance_m": 300,
        },
        "risk": {"flood_risk_score": 10},  # stands in for an integrated flood hazard source
        "evidence": [{"source_type": "satellite", "source_reference": "NASA AppEEARS HLS", "freshness": "derived"}],
        "opportunity": {"growth_score": 85},
        "location": {"district": "Pune"},
        "geometry": {"type": "Polygon"},
    }
    record.update(overrides)
    return record


def _evidenced_profile(name):
    """A profile with no weight on growth, which is never scorable from imagery."""
    profile = get_default_profile(name)
    weights = profile["weights"]
    freed = weights["growth_pct"]
    weights["growth_pct"] = 0
    weights["legal_safety_pct"] += freed
    return profile


def test_clean_parcel_is_buy_with_high_explainable_scores():
    result = compute_evaluation(parcel(), _evidenced_profile("investor"))
    assert result["recommendation"] == "BUY"
    assert result["growth_score"] is None, "growth is not derivable from spectral indices"
    assert sum(item["contribution"] for item in result["weighted_contributions"]) == result["composite_score"]
    assert "Location score" in result["reasoning_summary"] and "legal safety" in result["reasoning_summary"]
    assert "legal checks are verified" in result["reasoning_summary"], "BUY only with verified legal checks"


def test_flood_prone_parcel_passes_through_risk_as_low_flood_safety():
    safe = compute_evaluation(parcel(), _evidenced_profile("conservative"))
    flood_prone = compute_evaluation(parcel(risk={"flood_risk_score": 95}), _evidenced_profile("conservative"))
    assert flood_prone["flood_safety_score"] == 5
    assert flood_prone["composite_score"] < safe["composite_score"]


def test_terrain_indicator_alone_never_produces_a_flood_score():
    """Only an integrated hazard source may populate flood safety."""
    terrain_only = compute_evaluation(
        parcel(risk={"terrain_relative_elevation_score": 55, "elevation_m": 138.4}),
        _evidenced_profile("conservative"),
    )
    assert terrain_only["flood_safety_score"] is None
    assert "flood_safety" in terrain_only["unassessed_factors"]
    assert "flood_safety" not in {c["factor"] for c in terrain_only["weighted_contributions"]}


def test_encumbered_title_triggers_hard_avoid():
    record = parcel(land_records={"title_clear": False, "encumbrance_flag": True}, rera={"is_rera_project": False})
    result = compute_evaluation(record, _evidenced_profile("developer"))
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
    # growth carries no weight: it is never scorable from imagery alone, and a
    # weighted-but-unscored factor correctly withholds the composite.
    evaluation["weights"] = {"growth_pct": 0, "legal_safety_pct": 9, "accessibility_pct": 1, "flood_safety_pct": 0}
    result = compute_evaluation(parcel(), evaluation)
    weights = {item["factor"]: item["contribution"] for item in result["weighted_contributions"]}
    assert abs(result["composite_score"] - sum(weights.values())) < 0.01
    assert weights["legal_safety"] > weights["accessibility"]


def test_identical_evidence_can_produce_profile_specific_results():
    record = parcel(infrastructure={"nearest_road_distance_m": 200, "nearest_school_distance_m": 4500})
    homebuyer = compute_evaluation(record, _evidenced_profile("homebuyer"))
    investor = compute_evaluation(record, _evidenced_profile("investor"))
    assert homebuyer["accessibility_score"] != investor["accessibility_score"]
    assert homebuyer["composite_score"] != investor["composite_score"]


def test_missing_data_lowers_evidence_coverage_not_a_confidence_number() -> None:
    """Confidence was never a probability; coverage replaces it."""
    complete = compute_evaluation(parcel(), get_default_profile("conservative"))
    incomplete = compute_evaluation(
        {"risk": {"flood_risk_score": None}, "satellite": {"change_type": "insufficient_evidence"}},
        get_default_profile("conservative"),
    )
    assert complete["confidence"] is None and incomplete["confidence"] is None
    assert incomplete["assessed_weight_pct"] < complete["assessed_weight_pct"]
    assert incomplete["recommendation"] == "WAIT"


def test_sensitivity_reports_changed_factors_and_magnitude():
    baseline = get_default_profile("homebuyer")
    changed = get_default_profile("investor")
    result = evaluate_sensitivity(parcel(), baseline, changed)
    assert result["factors"]
    assert all({"factor", "baseline", "changed", "delta"} <= set(item) for item in result["factors"])



def test_missing_land_records_produce_no_legal_score_at_all() -> None:
    """Previously this emitted a high legal-safety number with a caveat."""
    evaluation = {"profile": "homebuyer", "property_type": "residential", "weights": {}, "preferences": {}}
    unverified = compute_verdict({"land_records": None}, evaluation)
    assert unverified["legal_safety_score"] is None
    assert unverified["recommendation"] == "WAIT"
    assert any("Ownership record" in check for check in unverified["pre_purchase_checks"])
    verified = compute_verdict({"land_records": {"title_clear": True, "encumbrance_flag": False}}, evaluation)
    assert "land records not provided" not in verified["reasoning_summary"]


def test_buy_needs_all_four_legal_checks_and_a_defect_is_walk_away() -> None:
    """Regression (2026-10-26): an unclear title plus an encumbrance summed to exactly the 70 limit and gave WAIT, and
    any matched record (even a defective one) counted as completed due diligence."""
    profile = _evidenced_profile("investor")
    defective = compute_evaluation(parcel(land_records={"title_clear": False, "encumbrance_flag": True}), profile)
    assert defective["recommendation"] == "AVOID" and "title is not clear and an encumbrance is recorded" in defective["reasoning_summary"]
    unclear = compute_evaluation(parcel(land_records={"title_clear": False, "encumbrance_flag": False,
                                                      "zoning_verified": True, "approvals_verified": True}), profile)
    assert unclear["recommendation"] == "AVOID"
    partial = compute_evaluation(parcel(land_records={"title_clear": True, "encumbrance_flag": False}), profile)
    assert partial["recommendation"] == "BUY", "a strong location is BUY, conditional on the remaining checks"
    assert "Buy only after the legal checks: verification of zoning, approvals" in partial["reasoning_summary"]
    complete = compute_evaluation(parcel(), profile)
    assert complete["recommendation"] == "BUY"


def test_recorded_legal_checks_are_never_verification_and_a_recorded_problem_is_walk_away() -> None:
    """The buyer's own records (2026-10-26): statements, not verification."""
    profile = _evidenced_profile("investor")
    mine = {k: {"outcome": "confirmed", "source": "portal", "checked_on": "2026-10-24"}
            for k in ("title", "encumbrance", "zoning", "approvals")}
    recorded = compute_evaluation(parcel(land_records=None, user_legal_checks=mine), profile)
    assert recorded["recommendation"] == "BUY", "strong location: conditional BUY"
    assert "you recorded it as checked on 2026-10-24; TerraScope cannot verify that" in recorded["reasoning_summary"],         "only matched official records verify: recorded checks stay named as pending"
    problem = dict(mine, encumbrance={"outcome": "problem", "source": "TNREGINET", "checked_on": "2026-10-24"})
    walk = compute_evaluation(parcel(land_records=None, user_legal_checks=problem), profile)
    assert walk["recommendation"] == "AVOID" and "you recorded a problem with the encumbrance check" in walk["reasoning_summary"]


# --- government and restricted land (2026-10-26): decided before any score, synthetic inputs only -------------

def _mapped(category, contact, name=None, overlap_m2=150.0, overlap_share=0.02):
    """An edge contact defaults to 2% of the plot: more than map error, so it still holds (see within_map_error)."""
    return {"status": "assessed", "uncertainty_m": 15, "data_as_of": "2026-10-04",
            "overlaps": [] if contact == "nearby" else [{"category": category, "category_label": category.title(), "name": name,
                                                          "contact": contact, "ownership_signal": "unknown",
                                                          "overlap_m2": overlap_m2, "overlap_share": overlap_share}],
            "nearby": [{"category": category, "contact": "nearby", "distance_m": 120.0}] if contact == "nearby" else []}


def _record(outcome, source="TN e-Services poramboke verification"):
    return {"check": "government_land", "outcome": outcome, "source": source, "survey_number": "123/4A", "checked_on": "2026-10-26"}


def test_mapped_overlap_with_a_high_court_or_stadium_warns_and_holds_a_strong_buy_at_wait() -> None:
    profile = _evidenced_profile("investor")
    assert compute_evaluation(parcel(), profile)["recommendation"] == "BUY", "baseline: strong and legally verified"
    stadium = compute_evaluation(parcel(public_land=_mapped("sports", "overlap", "City Stadium")), profile)
    assert stadium["recommendation"] == "WAIT", "never bought on a score"
    assert stadium["reasoning_summary"].startswith("WARNING:") and "not an ownership finding" in stadium["reasoning_summary"]
    assert stadium["government_land"]["status"] == "potential_public"
    court = compute_evaluation(parcel(public_land=_mapped("court", "overlap", "High Court")), profile)
    assert court["recommendation"] == "RESTRICTED", "a court is restricted land (2026-10-26)"


def test_a_parcel_near_a_stadium_but_outside_it_is_not_held() -> None:
    result = compute_evaluation(parcel(public_land=_mapped("sports", "nearby")), _evidenced_profile("investor"))
    assert result["recommendation"] == "BUY" and result["government_land"]["hold"] is False


def test_an_official_record_of_non_transferable_government_land_is_walk_away_whatever_the_score() -> None:
    result = compute_evaluation(parcel(user_government_land=[_record("government_non_transferable")]), _evidenced_profile("investor"))
    assert result["recommendation"] == "AVOID" and result["composite_score"] is None
    assert "non-transferable government land" in result["reasoning_summary"]
    blocked = compute_evaluation(parcel(user_government_land=[_record("restriction_prohibits_use")]), _evidenced_profile("investor"))
    assert blocked["recommendation"] == "AVOID"


def test_potential_public_land_without_an_official_record_holds_at_wait() -> None:
    result = compute_evaluation(parcel(public_land=_mapped("defence", "edge"), user_government_land=[_record("records_unavailable")]),
                                _evidenced_profile("investor"))
    assert result["recommendation"] == "WAIT" and result["government_land"]["status"] == "records_unavailable"


def test_an_edge_sliver_within_the_map_error_is_nearby_not_a_hold() -> None:
    """SRM, 2026-10-28: 140 m2 and 69 m2 of a 26-acre plot touched a mapped lake and park and the answer was WAIT."""
    profile = _evidenced_profile("investor")
    sliver = _mapped("water_body", "edge", overlap_m2=140.0, overlap_share=0.0013)
    sliver["overlaps"][0]["osm_id"] = "w67551369"
    result = compute_evaluation(parcel(public_land=sliver), profile)
    assert result["recommendation"] == "BUY" and result["government_land"]["hold"] is False
    assert result["government_land"]["within_map_error"] == ["w67551369"]
    wider = compute_evaluation(parcel(public_land=_mapped("water_body", "edge", overlap_m2=600.0, overlap_share=0.004)), profile)
    assert wider["recommendation"] == "WAIT", "500 m2 or more is more than a 15 m map error explains"


def _flood(height=None, seen=None, river=None):
    return {"river_flood": river, "terrain": {"elevation_above_nearest_water_m": height, "nearest_water_feature_class": "drain",
                                              "nearest_water_feature_distance_m": 94.0},
            "surface_water": {"parcel": {"water_ever_fraction": seen}}}


def test_unread_river_maps_add_a_flood_check_and_strong_water_signs_hold_a_buy() -> None:
    """User decision, 2026-10-28 (Pallikaranai: -0.6 m below a drain, water on 17% of the plot, was 'Buy after checks')."""
    profile = _evidenced_profile("investor")
    dry = compute_evaluation(parcel(flood_indicators=_flood(height=2.4, seen=0.0)), profile)
    assert dry["recommendation"] == "BUY" and any(c.startswith("Flood history") for c in dry["pre_purchase_checks"])
    low = compute_evaluation(parcel(flood_indicators=_flood(height=-0.6, seen=0.17)), profile)
    assert low["recommendation"] == "WAIT" and low["flood_unknown"]["strong"]
    assert "-0.6 m relative to the nearest mapped water (drain, 94 m away)" in low["reasoning_summary"]
    assert "17% of the plot" in low["reasoning_summary"]
    read = compute_evaluation(parcel(flood_indicators=_flood(height=-0.6, seen=0.17, river={"status": "assessed", "scenarios": []})),
                              profile)
    assert read["flood_unknown"] is None and not any(c.startswith("Flood history") for c in read["pre_purchase_checks"])


def test_conflicting_official_records_hold_at_wait_and_name_both() -> None:
    result = compute_evaluation(parcel(user_government_land=[_record("government_non_transferable", "A-register"),
                                                             _record("private_per_record", "Patta copy")]), _evidenced_profile("investor"))
    assert result["recommendation"] == "WAIT" and result["government_land"]["status"] == "records_conflicting"
    assert "A-register" in result["reasoning_summary"] and "Patta copy" in result["reasoning_summary"]


def test_a_documented_lawful_auction_or_transfer_is_not_rejected_for_being_government_land() -> None:
    result = compute_evaluation(parcel(user_government_land=[_record("government_transfer_documented", "Auction order G.O. 12")]),
                                _evidenced_profile("investor"))
    assert result["recommendation"] == "WAIT", "verify the order's conditions, but do not walk away"
    assert any("auction or assignment order" in c for c in result["pre_purchase_checks"])
    conditions = compute_evaluation(parcel(user_government_land=[_record("restriction_with_conditions", "Railway NOC rule")]),
                                    _evidenced_profile("investor"))
    assert conditions["recommendation"] == "WAIT"


def test_no_mapped_facility_or_missing_map_data_is_never_read_as_private_land() -> None:
    profile = _evidenced_profile("investor")
    for public in ({"status": "assessed", "overlaps": [], "nearby": []},
                   {"status": "unavailable", "overlaps": [], "nearby": [], "reason": "not built"}, None):
        result = compute_evaluation(parcel(land_records=None, public_land=public), profile)
        assert result["government_land"]["status"] == "ownership_unverified"
        assert "private" not in result["reasoning_summary"].lower() and "Buy only after the legal checks" in result["reasoning_summary"]
    other_state = compute_evaluation(parcel(land_records=None, location={"state": "Goa"}), profile)
    assert not any("Tamil Nadu" in c for c in other_state["pre_purchase_checks"]), "no state's portal is implied for another"


def test_missing_road_data_makes_accessibility_unknown_not_scored_from_schools() -> None:
    """All-India store without roads (2026-10-26): never a zero, never a school-only access score."""
    infra = {"nearest_road_distance_m": None, "nearest_school_distance_m": 400.0, "search_radius_m": 5000,
             "layer_status": {"road": "not_installed", "school": "installed"}}
    result = compute_evaluation(parcel(infrastructure=infra, location={"state": "Karnataka"}), _evidenced_profile("investor"))
    access = next(f for f in result["factors"] if f["factor"] == "accessibility")
    assert access["score"] is None and access["status"] == "unavailable"
    assert "road data is not installed for Karnataka" in access["basis"] and "fetch-data karnataka" in access["basis"]
    assert result["recommendation"] == "WAIT"


def test_a_material_overlap_with_mapped_restricted_land_is_restricted_and_not_scored() -> None:
    """User decision (2026-10-26): defence, railway, water body, court... land is not assessed for purchase."""
    profile = _evidenced_profile("investor")
    defence = _mapped("defence", "overlap", "Kalina Camp")
    defence["overlaps"][0]["overlap_share"] = 0.01
    result = compute_evaluation(parcel(public_land=defence), profile)
    assert result["recommendation"] == "RESTRICTED" and result["composite_score"] is None
    assert result["reasoning_summary"].startswith("RESTRICTED LAND") and "Kalina Camp" in result["reasoning_summary"]


def test_restricted_needs_a_material_overlap_of_a_restricted_category() -> None:
    profile = _evidenced_profile("investor")
    assert compute_evaluation(parcel(public_land=_mapped("sports", "overlap", "Stadium")), profile)["recommendation"] == "WAIT", \
        "a stadium's owner is not implied: potential overlap, not restricted"
    assert compute_evaluation(parcel(public_land=_mapped("defence", "edge")), profile)["recommendation"] == "WAIT", \
        "within the ±15 m uncertainty only: not restricted"
    defect = compute_evaluation(parcel(public_land=_mapped("defence", "overlap"), land_records={"title_clear": False}), profile)
    assert defect["recommendation"] == "AVOID", "a recorded legal defect still decides first"


def test_the_summary_is_clipped_at_a_sentence_never_mid_word() -> None:
    from scoring_engine._verdict import _clip

    text = "First sentence. " * 40
    clipped = _clip(text)
    assert len(clipped) <= 500 and clipped.endswith("sentence.")
    assert _clip("short") == "short"


def test_the_development_outlook_projects_with_a_range_and_a_disclaimer() -> None:
    from scoring_engine._outlook import development_outlook

    series = [(2017, 0.4378), (2018, 0.4486), (2019, 0.4987), (2020, 0.524), (2021, 0.5195), (2022, 0.5474), (2023, 0.5492)]
    out = development_outlook({"land_cover_history": {"surroundings": [{"year": y, "built_share_within_1km": s} for y, s in series]}})
    y2030 = out["projections"][-1]
    assert out["status"] == "growing_fast" and y2030["low"] < y2030["share"] < y2030["high"] <= 1.0
    assert 0.65 < y2030["share"] < 0.75 and "not a prediction of prices" in out["disclaimer"]
    full = development_outlook({"land_cover_history": {"surroundings": [{"year": y, "built_share_within_1km": 0.97} for y, _ in series]}})
    assert full["status"] == "built_out" and full["projections"][-1]["share"] <= 1.0
    assert development_outlook({})["status"] == "unavailable"

