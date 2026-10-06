"""Integration tests for valuation, evidence honesty and saved reports.

Run against a live Compose stack, like test_end_to_end.py:
    pytest tests/integration -v
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import httpx
import pytest

from test_end_to_end import EVALUATIONS, POLYGONS, analyse, client, evaluate  # noqa: F401


SQFT_PER_SQM = 10.763910416709722


# --- evidence honesty -----------------------------------------------------

def test_rera_district_match_is_never_reported_as_this_parcel_registration(client: httpx.Client) -> None:
    """A shared district is candidate evidence; it cannot prove registration."""
    snapshot = analyse(client, POLYGONS[0])
    rera = snapshot.get("rera") or {}
    assert rera.get("is_rera_project") is not True, (
        "the seed matches on district only, which is not proof this parcel is registered"
    )
    rows = [item for item in snapshot["evidence"] if item["source_type"] == "maharera_seed"]
    assert rows, "the RERA lookup should always leave a ledger row"
    assert "unknown" in rows[0]["summary"].lower()


def test_data_completeness_reflects_missing_evidence(client: httpx.Client) -> None:
    """No land-records connector exists, so completeness must not read 100%."""
    snapshot = analyse(client, POLYGONS[0])
    completeness = snapshot["metadata"]["data_completeness_pct"]
    assert completeness is not None
    assert completeness < 100.0, "completeness should account for evidence we never collected"


def test_malformed_pdf_is_stored_but_reported_as_not_indexed(client: httpx.Client) -> None:
    """An unreadable PDF must fail honestly rather than claim a silent success."""
    snapshot = analyse(client, POLYGONS[0])
    fixture = Path(__file__).parent / "fixtures" / "malformed.pdf"
    with fixture.open("rb") as handle:
        response = client.post(
            f"/api/v1/parcels/{snapshot['parcel_id']}/documents",
            files={"file": (fixture.name, handle, "application/pdf")},
            timeout=20.0,
        )
    assert response.status_code == 200, response.text
    assert response.json()["text_indexed"] is False


def test_unsupported_file_type_is_rejected(client: httpx.Client) -> None:
    snapshot = analyse(client, POLYGONS[0])
    response = client.post(
        f"/api/v1/parcels/{snapshot['parcel_id']}/documents",
        files={"file": ("payload.exe", b"MZ\x00\x01", "application/octet-stream")},
        timeout=20.0,
    )
    assert response.status_code == 400


def test_upload_after_an_evaluation_reaches_the_next_evaluation(client: httpx.Client) -> None:
    """The retrieval cache must not serve an answer that predates the upload."""
    snapshot = analyse(client, POLYGONS[1])
    parcel_id = snapshot["parcel_id"]
    first = evaluate(client, snapshot, EVALUATIONS[0])
    assert not [item for item in first["evidence"] if item["source_type"] == "user_upload"]

    fixture = Path(__file__).parent / "fixtures" / "title_evidence.txt"
    with fixture.open("rb") as handle:
        upload = client.post(
            f"/api/v1/parcels/{parcel_id}/documents",
            files={"file": (fixture.name, handle, "text/plain")},
            timeout=20.0,
        )
    assert upload.status_code == 200, upload.text

    second = evaluate(client, snapshot, EVALUATIONS[0])
    ledger = [item for item in second["evidence"] if item["source_type"] == "user_upload"]
    assert [item["source_reference"] for item in ledger] == [fixture.name], (
        "a document uploaded after the first evaluation must appear in the next one"
    )


def test_saved_reports_can_be_listed_and_reopened(client: httpx.Client) -> None:
    snapshot = analyse(client, POLYGONS[2])
    parcel_id = snapshot["parcel_id"]
    evaluate(client, snapshot, EVALUATIONS[0])

    listing = client.get("/api/v1/parcels", timeout=10.0)
    assert listing.status_code == 200
    mine = [item for item in listing.json()["reports"] if item["parcel_id"] == parcel_id]
    assert mine, "the analysed parcel should appear in the saved reports list"
    assert mine[0]["has_evaluation"] is True

    reopened = client.get(f"/api/v1/parcels/{parcel_id}", timeout=10.0)
    assert reopened.status_code == 200
    body = reopened.json()
    assert body["evidence_snapshot"]["geometry"] == snapshot["geometry"]
    assert body["latest_evaluation"] is not None


# --- valuation ------------------------------------------------------------

def request_valuation(client: httpx.Client, snapshot: dict[str, Any], **overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "latitude": snapshot["location"]["latitude"],
        "longitude": snapshot["location"]["longitude"],
        "area_sqft": snapshot["geometry_metadata"]["area_m2"] * SQFT_PER_SQM,
        "land_use": "residential",
        "price_basis": "transaction",
    }
    payload.update(overrides)
    response = client.post("/api/v1/valuation/estimate", json=payload, timeout=30.0)
    assert response.status_code == 200, response.text
    return response.json()


def test_valuation_model_endpoint_reports_its_provenance(client: httpx.Client) -> None:
    status = client.get("/api/v1/valuation/model", timeout=15.0).json()
    if not status["available"]:
        assert status["reason"] == "model_not_trained"
        return
    assert status["model_version"] and status["data_version"]
    validation = status["validation"]
    assert validation["strategy"] in {"temporal", "geographic"}
    # Accuracy is measured against a baseline, never asserted.
    assert validation["model"]["mae_inr_per_sqft"] > 0
    assert validation["baseline"]["mae_inr_per_sqft"] > 0
    assert validation["holdout_rows"] >= 10


def test_valuation_returns_a_price_or_an_explicit_unavailable(client: httpx.Client) -> None:
    snapshot = analyse(client, POLYGONS[0])
    result = request_valuation(client, snapshot)
    if result["status"] == "unavailable":
        assert result["reason"] in {"model_not_trained", "location_not_covered", "land_use_not_covered", "synthetic_model_only"}
        assert result["detail"]
        return
    assert result["estimated_inr_per_sqft"] > 0
    assert result["estimated_total_inr"] > 0
    assert result["model_version"] and result["data_version"] and result["valuation_date"]
    assert result["evidence_coverage"]["observations_within_radius"] >= 1
    # A range is only present when its measured holdout coverage justified it.
    if result["range"] is None:
        assert result["range_unavailable_reason"]
    else:
        assert result["range"]["low_inr_per_sqft"] <= result["estimated_inr_per_sqft"] <= result["range"]["high_inr_per_sqft"]


def test_unsupported_location_is_refused_rather_than_guessed(client: httpx.Client) -> None:
    """A sub-antarctic island is nowhere near any comparable sale."""
    response = client.post(
        "/api/v1/valuation/estimate",
        json={"latitude": -54.5, "longitude": 158.9, "area_sqft": 2000, "land_use": "residential", "price_basis": "transaction"},
        timeout=30.0,
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "unavailable"
    assert body["reason"] in {"location_not_covered", "model_not_trained", "synthetic_model_only"}
    assert body["detail"]


def test_invalid_valuation_input_is_a_client_error(client: httpx.Client) -> None:
    response = client.post(
        "/api/v1/valuation/estimate",
        json={"latitude": 18.52, "longitude": 73.85, "area_sqft": 2000, "land_use": "spaceport", "price_basis": "transaction"},
        timeout=15.0,
    )
    assert response.status_code == 400


def test_changing_suitability_weights_does_not_move_the_market_price(client: httpx.Client) -> None:
    """The headline requirement: a preference slider must not reprice the land."""
    snapshot = analyse(client, POLYGONS[0])
    snapshot_id = snapshot["metadata"]["analysis_snapshot_id"]

    before = request_valuation(client, snapshot)
    conservative = evaluate(client, snapshot, EVALUATIONS[2])
    aggressive = evaluate(client, snapshot, {
        **EVALUATIONS[2],
        "weights": {"growth_pct": 70, "legal_safety_pct": 10, "accessibility_pct": 10, "flood_safety_pct": 10},
    })
    after = request_valuation(client, snapshot)

    assert before == after, "an identical valuation request must return an identical result"

    # The weights really did reach the suitability side, so this is a real comparison.
    assert conservative["evaluation"]["weights"] != aggressive["evaluation"]["weights"]
    # The composite is withheld when evidence is thin (067d541); the per-factor weighted
    # contributions are always computed, so compare those, and the composites when both exist.
    assert conservative["score_breakdown"]["weighted_contributions"] != aggressive["score_breakdown"]["weighted_contributions"]
    if conservative["score_breakdown"]["composite_score"] is not None and aggressive["score_breakdown"]["composite_score"] is not None:
        assert conservative["score_breakdown"]["composite_score"] != aggressive["score_breakdown"]["composite_score"]

    # Re-scoring must not have re-collected or mutated the evidence.
    stored = client.get(f"/api/v1/analysis/{snapshot_id}", timeout=10.0)
    assert stored.status_code == 200
    assert stored.json() == snapshot
    for result in (conservative, aggressive):
        assert result["geometry"] == snapshot["geometry"]
        assert result["satellite"] == snapshot["satellite"]
        assert result["infrastructure"] == snapshot["infrastructure"]
        assert result["rera"] == snapshot["rera"]


def test_property_facts_may_move_the_price_even_though_preferences_may_not(client: httpx.Client) -> None:
    snapshot = analyse(client, POLYGONS[0])
    residential = request_valuation(client, snapshot, land_use="residential")
    commercial = request_valuation(client, snapshot, land_use="commercial")
    if residential["status"] != "available" or commercial["status"] != "available":
        pytest.skip("valuation unavailable for this parcel")
    assert residential["land_use"] == "residential"
    assert commercial["land_use"] == "commercial"


def test_total_value_is_price_times_area(client: httpx.Client) -> None:
    snapshot = analyse(client, POLYGONS[0])
    result = request_valuation(client, snapshot)
    if result["status"] != "available":
        pytest.skip("valuation unavailable for this parcel")
    assert result["estimated_total_inr"] == pytest.approx(
        result["estimated_inr_per_sqft"] * result["area_sqft"], rel=1e-6
    )


def test_synthetic_models_are_flagged_so_the_ui_can_label_them(client: httpx.Client) -> None:
    """Demo data must never be presentable as a real valuation."""
    status = client.get("/api/v1/valuation/model", timeout=15.0).json()
    if not status["available"]:
        pytest.skip("no model trained")
    assert isinstance(status["is_synthetic"], bool)
    snapshot = analyse(client, POLYGONS[0])
    result = request_valuation(client, snapshot)
    if result["status"] == "available":
        assert result["is_synthetic"] == status["is_synthetic"]
