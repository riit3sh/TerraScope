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
    assert verdict["recommendation"] == "INSUFFICIENT_EVIDENCE"
    evidence_ids = {row["evidence_id"] for row in result["evidence"]}
    assert verdict["citations"], "collected evidence must be citable without an LLM"
    for citation in verdict["citations"]:
        assert citation["evidence_id"] in evidence_ids and citation["claim"]
    cited = {c["evidence_id"].rsplit(":", 1)[-1] for c in verdict["citations"]}
    assert {"osm", "river-flood", "surface-water", "water-features"} <= cited
    # Absence of land records is not cited: there is nothing to cite.
    assert not any("land record" in c["claim"].lower() for c in verdict["citations"])


def test_uploaded_document_is_cited_by_page_and_never_verifies_title() -> None:
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
    doc_cites = [c for c in result["verdict"]["citations"] if c["source_type"] == "user_upload"]
    assert {(c["claim"].split()[0], c["location"]) for c in doc_cites} == {("Survey", "page 2"), ("Village", "page 2")}
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
    assert by_area["Rainfall waterlogging and coastal flooding"]["assessment"] == "unknown"
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
    rain = next(f for f in findings if f["area"].startswith("Rainfall waterlogging"))
    assert rain["assessment"] == "unknown" and rain["finding"].startswith("Not assessed")
    for f in findings:
        assert f.get("source") or f["basis"] in ("not_verified", "unavailable", "user_provided"), f["area"]
        assert f["next_step"], f["area"]
    assert result["verdict"]["recommendation"] != "BUY", "no matched land records: never BUY"
