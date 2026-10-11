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
# These run against whatever price data the stack serves. With none loaded (the
# current state), every estimate must be an explicit refusal.

REFUSALS = {"no_price_data", "price_data_invalid", "price_type_not_covered", "land_use_not_covered",
            "no_comparables_nearby", "stale_data_only", "area_outside_support", "insufficient_comparables"}


def request_valuation(client: httpx.Client, snapshot: dict[str, Any], **overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "latitude": snapshot["location"]["latitude"],
        "longitude": snapshot["location"]["longitude"],
        "area_sqft": snapshot["geometry_metadata"]["area_m2"] * SQFT_PER_SQM,
        "land_use": "residential",
        "price_basis": "asking",
    }
    payload.update(overrides)
    response = client.post("/api/v1/valuation/estimate", json=payload, timeout=30.0)
    assert response.status_code == 200, response.text
    return response.json()


def test_valuation_data_endpoint_reports_what_is_loaded(client: httpx.Client) -> None:
    status = client.get("/api/v1/valuation/data", timeout=15.0).json()
    if not status["available"]:
        assert status["reason"] in {"no_price_data", "price_data_invalid"} and status["detail"]
        return
    assert status["data_version"] and status["data"]["sources"]
    assert set(status["data"]["price_types"]) <= {"asking", "transaction", "guideline"}


def test_valuation_returns_a_comparable_range_or_an_explicit_refusal(client: httpx.Client) -> None:
    snapshot = analyse(client, POLYGONS[0])
    result = request_valuation(client, snapshot)
    if result["status"] == "unavailable":
        assert result["reason"] in REFUSALS and result["detail"]
        return
    assert result["price_type"] == "asking" and "not completed sales" in result["price_type_label"]
    assert result["comparable_count"] >= 5 and result["comparables"]
    spread = result["spread_inr_per_sqft"]
    assert spread["min"] <= spread["p25"] <= result["estimate_inr_per_sqft"] <= spread["p75"] <= spread["max"]
    assert "not a statistically validated prediction interval" in result["spread_basis"]
    assert result["data_version"] and result["validation"]["status"]


def test_unsupported_location_is_refused_rather_than_guessed(client: httpx.Client) -> None:
    """A sub-antarctic island is nowhere near any comparable."""
    response = client.post(
        "/api/v1/valuation/estimate",
        json={"latitude": -54.5, "longitude": 158.9, "area_sqft": 2000, "land_use": "residential", "price_basis": "asking"},
        timeout=30.0,
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "unavailable" and body["reason"] in REFUSALS and body["detail"]


def test_invalid_valuation_input_is_a_client_error(client: httpx.Client) -> None:
    for payload in ({"land_use": "spaceport"}, {"price_basis": "rumour"}):
        response = client.post(
            "/api/v1/valuation/estimate",
            json={"latitude": 12.95, "longitude": 79.14, "area_sqft": 2000, "land_use": "residential",
                  "price_basis": "asking", **payload},
            timeout=15.0,
        )
        assert response.status_code == 400, response.text  # even with no price data loaded


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


def test_total_is_rate_times_area_when_shown(client: httpx.Client) -> None:
    snapshot = analyse(client, POLYGONS[0])
    result = request_valuation(client, snapshot)
    if result["status"] != "available" or result["total_inr"] is None:
        pytest.skip("no total for this parcel")
    assert result["total_inr"]["estimate"] == pytest.approx(result["estimate_inr_per_sqft"] * result["area_sqft"], rel=1e-3)
