"""Regression tests built on the acceptance report: VIT Vellore, snapshot 568d1f42 (saved 2026-10-12).

The fixture is that report's stored evidence snapshot, unchanged. Each test pins a defect the
report showed: ignored accessibility preferences, a rule-based summary labelled "grounded AI",
and uploaded documents that could never be referenced.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from citations import find_mentions
from pipeline import evaluate_snapshot
from scoring_engine.scoring import accessibility_components

VIT = json.loads((Path(__file__).parent / "fixtures" / "vit_snapshot_568d1f42.json").read_text(encoding="utf-8"))
SETTINGS = {
    "profile": "homebuyer", "property_type": "residential", "investment_horizon": "1_to_3y",
    "weights": {"growth_pct": 20, "legal_safety_pct": 35, "accessibility_pct": 25, "flood_safety_pct": 20},
    "preferences": {"road_importance": "medium", "school_importance": "high", "max_road_distance_m": 3000,
                    "max_school_distance_m": 5000, "rera_requirement": "important"},
}


@pytest.fixture(autouse=True)
def no_ai(monkeypatch):
    monkeypatch.delenv("GROQ_API_KEY", raising=False)


def _with_preferences(**preferences):
    return {**SETTINGS, "preferences": {**SETTINGS["preferences"], **preferences}}


def _factor(result, name):
    return next(f for f in result["score_breakdown"]["factors"] if f["factor"] == name)


def test_accessibility_preferences_change_the_score_and_nothing_is_recollected() -> None:
    snapshot = copy.deepcopy(VIT)
    wide = evaluate_snapshot(snapshot, SETTINGS)
    tight = evaluate_snapshot(snapshot, _with_preferences(max_road_distance_m=500, max_school_distance_m=1000))
    assert wide["score_breakdown"]["accessibility_score"] == 90.25  # the saved report's figure
    assert tight["score_breakdown"]["accessibility_score"] < 50
    contributions = {c["factor"]: c["contribution"] for c in tight["score_breakdown"]["weighted_contributions"]}
    # The only scored factor carries all of the scored weight.
    assert contributions["accessibility"] == tight["score_breakdown"]["accessibility_score"]
    # Same immutable evidence: evaluation never touches collected sections.
    for section in ("satellite", "infrastructure", "flood_indicators", "geometry", "metadata"):
        assert tight[section] == wide[section] == VIT[section]
    access = _factor(tight, "accessibility")
    assert "accepted but not applied" not in access["limitations"]
    assert "500 m limit" in access["basis"] and "1,000 m limit" in access["basis"]
    assert access["details"]["road"]["cap_m"] == 500


def test_old_snapshot_says_its_distances_are_from_the_centroid() -> None:
    access = _factor(evaluate_snapshot(copy.deepcopy(VIT), SETTINGS), "accessibility")
    assert "125 m from the parcel centroid" in access["basis"]


def test_parcel_edge_distance_is_preferred_when_recorded() -> None:
    record = copy.deepcopy(VIT)
    record["infrastructure"]["nearest_road_distance_from_boundary_m"] = 0.0  # a road along the frontage
    parts = accessibility_components(record, SETTINGS["preferences"])
    assert parts["road"]["measured_from"] == "parcel boundary" and parts["road"]["sub_score"] == 100.0
    assert parts["road"]["centroid_distance_m"] == 125.15


def test_an_unmapped_feature_is_unknown_never_scored_as_confirmed_absence() -> None:
    """Regression (Senjeri, 2026-10-26): no school in OpenStreetMap within 5 km scored 0, as if confirmed absent."""
    record = copy.deepcopy(VIT)
    record["infrastructure"]["nearest_school_distance_m"] = None  # none mapped within the 5 km search
    parts = accessibility_components(record, {"max_school_distance_m": 3000})
    assert parts["school"]["sub_score"] is None and "not confirmed absent" in parts["school"]["measured_from"]
    assert parts["score"] == parts["road"]["sub_score"], "the score rests on what is mapped"
    record["infrastructure"]["nearest_road_distance_m"] = None
    assert accessibility_components(record, {})["score"] is None, "nothing mapped: unknown, not zero"
    findings = evaluate_snapshot(copy.deepcopy(record), SETTINGS)["verdict"]["findings"]
    access = next(f for f in findings if f["area"] == "Road and school access")
    assert access["assessment"] != "ok"


def test_rule_based_summary_is_labelled_and_cites_collected_evidence() -> None:
    result = evaluate_snapshot(copy.deepcopy(VIT), SETTINGS)
    verdict = result["verdict"]
    assert verdict["explanation_source"] == "deterministic"
    assert verdict["recommendation"] == "WAIT"
    evidence_ids = {row["evidence_id"] for row in result["evidence"]}
    assert verdict["citations"], "collected evidence must be citable without an LLM"
    for citation in verdict["citations"]:
        assert citation["evidence_id"] in evidence_ids and citation["claim"]
    cited = {c["evidence_id"].rsplit(":", 1)[-1] for c in verdict["citations"]}
    assert {"osm", "river-flood", "surface-water", "water-features"} <= cited
    # Absence of land records is not cited: there is nothing to cite.
    assert not any("land record" in c["claim"].lower() for c in verdict["citations"])


def test_legacy_uploaded_document_is_ignored_and_never_verifies_title() -> None:
    snapshot = copy.deepcopy(VIT)
    snapshot["uploaded_documents"] = [{
        "source_reference": "EC_2024.pdf", "source_type": "user_upload",
        "text": "Encumbrance certificate\fVillage: Brammapuram. S.No. 123/4A, extent 2.75 acres\fNil encumbrance",
    }]
    snapshot["user_land_details"] = {
        "state": "Tamil Nadu", "district": "Vellore", "taluk": "Katpadi", "village": "Brammapuram",
        "survey_number": "123", "subdivision": "4A",
        "documents": [{"filename": "EC_2024.pdf", "doc_type": "encumbrance_certificate", "text_extracted": True, "pages": 3}],
    }
    result = evaluate_snapshot(snapshot, SETTINGS)
    legal = _factor(result, "legal_safety")
    assert legal["score"] is None and legal["status"] == "unavailable"
    assert result["land_records"] is None  # a user claim never becomes a matched record
    assert "not independently verified" in legal["basis"] and "title is not verified" in legal["basis"]
    assert not any(c["source_type"] == "user_upload" for c in result["verdict"]["citations"])
    assert result["user_land_details"]["verification_status"] == "user_provided_unverified"


def test_a_bare_survey_number_needs_a_survey_label_to_count() -> None:
    details = {"survey_number": "45"}
    assert find_mentions("Total 45 acres; plot 45", details) == []
    assert find_mentions("Survey No. 45 of Brammapuram", details)[0]["field"] == "survey_number"
    assert find_mentions("S.F.No.45", details)[0]["field"] == "survey_number"


def test_old_v1_change_label_is_not_restated_as_a_seasonal_finding() -> None:
    """Regression: re-evaluating the v1 snapshot cited 'no change between same-season images' - v1 compared no seasons."""
    result = evaluate_snapshot(copy.deepcopy(VIT), SETTINGS)
    growth = _factor(result, "growth")
    assert "same-season" not in growth["basis"] and "Analyse the same boundary again" in growth["basis"]
    assert not any(c["evidence_id"].endswith(":statistical-change") for c in result["verdict"]["citations"])


def test_legal_names_the_state_from_the_boundary_when_geocoding_gave_none() -> None:
    legal = _factor(evaluate_snapshot(copy.deepcopy(VIT), SETTINGS), "legal_safety")
    assert "(Tamil Nadu)" in legal["basis"] and "RERA authority for Tamil Nadu" in legal["limitations"]


@pytest.mark.parametrize("first_share, status", [(0.63, "indicative"), (0.98, "established")])
def test_every_area_growth_status_passes_schema_validation(first_share: float, status: str) -> None:
    """Regression: a built-out area (central Chennai) failed schema validation on every evaluation."""
    trend = {"first_year": 2017, "first_share": first_share, "last_year": 2023, "last_share": first_share,
             "years_used": 7, "slope_pts_per_year": 0.0}
    snapshot = {**copy.deepcopy(VIT), "land_cover_history": {"status": "assessed", "trend_within_1km": trend,
                                                             "trend_1_to_3km": trend, "parcel": []}}
    result = evaluate_snapshot(snapshot, SETTINGS)  # schema-validated inside
    assert _factor(result, "growth")["status"] == status
    assert result["verdict"]["recommendation"] in {"BUY", "WAIT"}


def test_findings_put_red_flags_first_and_never_call_missing_evidence_ok() -> None:
    snapshot = copy.deepcopy(VIT)
    snapshot["flood_indicators"]["river_flood"]["scenarios"][1]["flooded_share_of_parcel"] = 0.6  # 1-in-20
    snapshot["flood_indicators"]["river_flood"]["scenarios"][1]["flooded_area_m2"] = 6000.0
    findings = evaluate_snapshot(snapshot, SETTINGS)["verdict"]["findings"]  # schema-validated inside
    assert findings[0]["area"] == "River flooding" and findings[0]["assessment"] == "red_flag"
    assert "1-in-20-year" in findings[0]["finding"] and findings[0]["basis"] == "modelled"
    by_area = {f["area"]: f for f in findings}
    assert by_area["Title and ownership"]["assessment"] == "unknown"  # no land-records source: never ok
    assert by_area["RERA registration"]["assessment"] == "unknown"
    assert by_area["Rainfall waterlogging"]["assessment"] == "unknown" and by_area["Coastal flooding"]["assessment"] == "unknown"
    assert all(f["next_step"] for f in findings)
    assert by_area["River flooding"]["as_of"] == "2026-01-12"  # the model release, not today


def test_recorded_legal_checks_pass_schema_validation_and_stay_the_buyers_statement() -> None:
    """Regression (2026-10-26): the evidence schema rejected user_legal_checks, so re-evaluation failed."""
    snapshot = copy.deepcopy(VIT)
    snapshot["user_legal_checks"] = {"encumbrance": {"check": "encumbrance", "outcome": "confirmed", "source": "TNREGINET",
                                                     "checked_on": "2026-10-26", "recorded_at": "2026-10-26T05:00:00+00:00"}}
    result = evaluate_snapshot(snapshot, SETTINGS)
    assert result["land_records"] is None and result["verdict"]["recommendation"] != "BUY"
    title = next(f for f in result["verdict"]["findings"] if f["area"] == "Title and ownership")
    assert title["assessment"] == "unknown" and "TerraScope cannot verify your records" in title["finding"]
    snapshot["user_legal_checks"]["zoning"] = {"check": "zoning", "outcome": "problem", "source": "DTCP", "checked_on": "2026-10-26"}
    walk = evaluate_snapshot(snapshot, SETTINGS)
    title = next(f for f in walk["verdict"]["findings"] if f["area"] == "Title and ownership")
    assert walk["verdict"]["recommendation"] == "AVOID" and title["assessment"] == "red_flag", "findings agree with the verdict"


def test_a_mapped_public_facility_overlap_passes_schema_validation_and_holds_the_decision() -> None:
    """Regression (2026-10-26): the schema rejected the 'mapped' basis, so an overlap made evaluation fail."""
    snapshot = copy.deepcopy(VIT)
    snapshot["public_land"] = {"status": "assessed", "uncertainty_m": 15, "data_as_of": "2026-10-04", "nearby": [],
                               "overlaps": [{"category": "sports", "category_label": "Stadium or sports ground", "name": "Synthetic Stadium",
                                             "contact": "overlap", "overlap_share": 0.6, "ownership_signal": "unknown"}]}
    result = evaluate_snapshot(snapshot, SETTINGS)
    row = next(f for f in result["verdict"]["findings"] if f["area"] == "Government and restricted land")
    assert row["basis"] == "mapped" and row["assessment"] == "caution"
    assert result["verdict"]["government_land"]["status"] == "potential_public" and result["verdict"]["recommendation"] != "BUY"


def test_unsupported_flood_types_are_not_assessed_and_every_finding_names_its_source() -> None:
    result = evaluate_snapshot(copy.deepcopy(VIT), SETTINGS)
    findings = result["verdict"]["findings"]
    for area in ("Rainfall waterlogging", "Coastal flooding"):
        row = next(f for f in findings if f["area"] == area)
        assert row["assessment"] == "unknown" and row["finding"].startswith("NOT ASSESSED"), area
    assert "not evidence that the plot stays dry" in next(f for f in findings if f["area"] == "Rainfall waterlogging")["finding"]
    for f in findings:
        assert f.get("source") or f["basis"] in ("not_verified", "unavailable", "user_provided"), f["area"]
        assert f["next_step"], f["area"]
    assert result["verdict"]["recommendation"] != "BUY", "no matched land records: never BUY"


def test_restricted_land_passes_schema_validation_and_names_the_overlap() -> None:
    snapshot = copy.deepcopy(VIT)
    snapshot["public_land"] = {"status": "assessed", "uncertainty_m": 15, "data_as_of": "2026-10-25", "nearby": [],
                               "overlaps": [{"category": "defence", "category_label": "Defence / military area", "name": "Synthetic Camp",
                                             "contact": "overlap", "overlap_share": 0.3, "ownership_signal": "government_tagged"}]}
    result = evaluate_snapshot(snapshot, SETTINGS)
    assert result["verdict"]["recommendation"] == "RESTRICTED" and "Synthetic Camp" in result["verdict"]["reasoning_summary"]
    row = next(f for f in result["verdict"]["findings"] if f["area"] == "Government and restricted land")
    assert row["assessment"] == "red_flag"


def _rera_row(state, mine=None, seller=None):
    snapshot = copy.deepcopy(VIT)
    snapshot["location"]["state"] = state
    if mine:
        snapshot["user_legal_checks"] = {"rera": {"check": "rera", "source": "state RERA portal", "checked_on": "2026-10-27", **mine}}
    if seller:
        snapshot["user_land_details"] = {"seller_type": seller}
    findings = evaluate_snapshot(snapshot, SETTINGS)["verdict"]["findings"]
    return next(f for f in findings if f["area"] == "RERA registration"), next(f for f in findings if f["area"] == "Title and ownership")


def test_rera_depends_on_who_is_selling_and_never_marks_a_plot_exempt_itself() -> None:
    row, title = _rera_row("Karnataka", seller="developer")
    assert row["assessment"] == "caution" and "likely needs RERA registration" in row["finding"]
    assert "https://rera.karnataka.gov.in" in row["next_step"] and "s. 3(2)" in row["finding"]
    assert title["basis"] == "not_verified", "the seller answer is not a land-record claim"
    row, _ = _rera_row("Karnataka", seller="individual")
    assert row["assessment"] == "unknown" and "may not apply to an ordinary resale" in row["finding"] and "Not marked exempt" in row["finding"]
    row, _ = _rera_row("Karnataka", seller="unsure")
    assert row["finding"].startswith("Not verified") and "who is selling is not known" in row["finding"]
    row, _ = _rera_row("Karnataka")
    assert row["finding"].startswith("Not verified") and row["basis"] == "not_verified"


def test_rera_outcomes_stay_the_buyers_record_and_never_mean_unregistered() -> None:
    row, _ = _rera_row("Karnataka", {"outcome": "registration_found", "reference": "PRM/KA/RERA/1251/123", "project_name": "Green Acres",
                                     "promoter_name": "ABC Developers"}, seller="developer")
    assert "Matching registration reported by you" in row["finding"] and "not verified by TerraScope" in row["finding"]
    assert "no. PRM/KA/RERA/1251/123, project Green Acres, promoter ABC Developers" in row["finding"]
    assert row["assessment"] == "unknown" and row["basis"] == "user_provided" and row["as_of"] == "2026-10-27"
    row, _ = _rera_row("Karnataka", {"outcome": "not_found_in_search", "project_name": "Green Acres"}, seller="developer")
    assert row["finding"].startswith("Not found in your search") and "not proof the project is unregistered" in row["finding"]
    assert row["assessment"] == "caution", "a promoter's sale with no registration found is flagged for verification"
    row, _ = _rera_row("Karnataka", {"outcome": "not_found_in_search"}, seller="individual")
    assert row["assessment"] == "unknown"
    row, _ = _rera_row("Karnataka", {"outcome": "unable_to_verify", "notes": "portal timed out"})
    assert "Unable to verify" in row["finding"] and "portal timed out" in row["finding"] and '"unregistered"' in row["finding"]
    row, _ = _rera_row("Karnataka", {"outcome": "not_applicable", "notes": "a single resale plot, not a layout"})
    assert row["finding"].startswith("Not applicable, as recorded by you") and "a single resale plot" in row["finding"]
    row, _ = _rera_row("Karnataka", {"outcome": "not_found"})  # a record made before 2026-10-27
    assert row["finding"].startswith("Not found in your search"), "legacy records still read"


def test_the_portal_follows_the_state_the_project_is_registered_in() -> None:
    row, _ = _rera_row("Tamil Nadu", {"outcome": "unable_to_verify", "rera_state": "Maharashtra"})
    assert "https://maharera.maharashtra.gov.in/" in row["next_step"]


def test_rera_cannot_decide_buy_or_walk_away_on_its_own() -> None:
    weak = copy.deepcopy(VIT)
    weak["user_legal_checks"] = {"rera": {"check": "rera", "outcome": "registration_found", "reference": "X1", "source": "portal", "checked_on": "2026-10-27"}}
    weak["land_cover_history"] = None  # no growth evidence: the location cannot be strong
    assert evaluate_snapshot(weak, SETTINGS)["verdict"]["recommendation"] != "BUY", "a registration found never makes BUY"
    for outcome in ("not_found_in_search", "unable_to_verify"):
        snap = copy.deepcopy(VIT)
        snap["user_land_details"] = {"seller_type": "developer"}
        snap["user_legal_checks"] = {"rera": {"check": "rera", "outcome": outcome, "source": "portal", "checked_on": "2026-10-27"}}
        assert evaluate_snapshot(snap, SETTINGS)["verdict"]["recommendation"] != "AVOID", outcome


def test_regions_without_a_portal_say_so_instead_of_inventing_one() -> None:
    row, title = _rera_row("Ladakh")
    assert "Website Not Setup" in row["next_step"] and "http" not in row["next_step"]
    assert "No checked land-records portal is listed for Ladakh" in title["next_step"]
    _, title = _rera_row("Maharashtra")
    assert "https://bhulekh.mahabhumi.gov.in/" in title["next_step"] and "verifies nothing" in title["next_step"]
    assert "encumbrance certificate" in title["next_step"] and title["assessment"] == "unknown"


def test_a_missing_portal_list_reads_as_unknown_not_as_no_portal(monkeypatch) -> None:
    import official_portals

    monkeypatch.setattr(official_portals, "_regions", lambda: {})
    row, title = _rera_row("Karnataka")
    assert "MoHUA lists them" in row["next_step"] and "Website Not Setup" not in row["next_step"]
    assert "ask the taluk / tehsil office" in title["next_step"]


def _coastal_rows(coast_info, elevation=None):
    snapshot = copy.deepcopy(VIT)
    snapshot["coast"] = coast_info
    if coast_info and coast_info.get("status") == "assessed" and not coast_info.get("coastal"):  # as the pipeline marks it
        for c in snapshot["flood_indicators"]["components"]:
            if c["mechanism"] == "coastal_flooding":
                c["status"] = "not_applicable"
    if elevation is not None:
        snapshot.setdefault("risk", {})["elevation_m"] = elevation
    result = evaluate_snapshot(snapshot, SETTINGS)
    return [f for f in result["verdict"]["findings"] if f["area"] == "Coastal flooding"], result


def test_coastal_flooding_appears_only_for_plots_near_the_sea() -> None:
    inland, result = _coastal_rows({"status": "assessed", "coastal": False, "distance_m": None, "beyond_m": 50000, "band_m": 10000})
    assert inland == [], "inland: no coastal-flooding row at all"
    flood = next(f for f in result["score_breakdown"]["factors"] if f["factor"] == "flood_safety")
    assert not any("Storm-surge" in c for c in flood["checklist"]), "and no missing-coastal-data checklist item"
    coastal, _ = _coastal_rows({"status": "assessed", "coastal": True, "distance_m": 560.0, "band_m": 10000, "data_as_of": "2026-10-25"}, elevation=4.0)
    assert coastal[0]["finding"].startswith("NOT ASSESSED: the plot is 0.6 km from the sea at about 4 m elevation")
    assert coastal[0]["assessment"] == "caution"
    unknown, _ = _coastal_rows(None)
    assert unknown and "distance to the sea is unknown" in unknown[0]["finding"], "old reports: unknown, never 'inland'"
