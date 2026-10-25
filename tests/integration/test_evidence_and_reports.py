"""Integration tests for evidence honesty, documents and saved reports.

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
    rows = [item for item in snapshot["evidence"] if item["source_type"] in ("maharera_seed", "rera")]
    assert rows, "the RERA lookup should always leave a ledger row"
    assert "unknown" in rows[0]["summary"].lower()
    # Regression (VIT report): a Tamil Nadu parcel was shown a "MahaRERA static seed" row.
    assert rows[0]["source_type"] == "rera" and "does not apply here" in rows[0]["summary"]


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


def test_land_price_estimation_is_not_offered(client: httpx.Client) -> None:
    """Land prices are out of scope for this version: no permitted, verified price data exists."""
    assert client.post("/api/v1/valuation/estimate", json={}, timeout=10.0).status_code == 404
    assert client.get("/api/v1/valuation/data", timeout=10.0).status_code == 404
