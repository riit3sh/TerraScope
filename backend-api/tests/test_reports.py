"""Saved reports keep the flood assessment; outside-India answers save nothing.

Every test points BACKEND_STORE_PATH at a temporary file, so the user's saved
reports in .local-ui-check/backend.sqlite3 are never read or written.
"""

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "backend-api"), str(ROOT / "backend-api" / "src")]

from routers import parcels, store  # noqa: E402

POLYGON = {"type": "Polygon", "coordinates": [[[78.82, 14.47], [78.821, 14.47], [78.821, 14.471], [78.82, 14.471], [78.82, 14.47]]]}
FLOOD = {
    "scoring_status": "not_scored",
    "assessment_status": "partial",
    "components": [
        {"mechanism": "river_flooding", "status": "assessed", "source": "JRC", "period": "modelled", "resolution": "~90 m",
         "coverage_share": 1.0, "summary": "Modelled river inundation first reaches the parcel in the 1-in-100-year scenario."},
        {"mechanism": "rainfall_waterlogging", "status": "not_assessed", "source": None, "period": None, "resolution": None,
         "coverage_share": None, "summary": "Not assessed."},
    ],
    "river_flood": {"status": "assessed", "scenarios": [{"return_period_years": 100, "flooded_share_of_parcel": 0.42}]},
}


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("BACKEND_STORE_PATH", str(tmp_path / "isolated.sqlite3"))
    store.init_store()
    from terrascope_backend_api.main import app

    return TestClient(app)


def test_partial_flood_assessment_survives_save_and_reopen(client, tmp_path) -> None:
    snapshot = {
        "parcel_id": "parcel-test-1",
        "location": {"address": "Kadapa, Andhra Pradesh"},
        "geometry": POLYGON,
        "geometry_metadata": {"area_acres": 2.9},
        "flood_indicators": FLOOD,
        "metadata": {"analysis_snapshot_id": "snap-test-1", "analysis_date_from": "2025-01-01", "analysis_date_to": "2026-01-01"},
    }
    store.save_snapshot(snapshot)

    listed = client.get("/api/v1/parcels").json()["reports"]
    assert [report["parcel_id"] for report in listed] == ["parcel-test-1"]
    reopened = client.get("/api/v1/parcels/parcel-test-1").json()
    assert reopened["evidence_snapshot"]["flood_indicators"] == FLOOD
    assert (tmp_path / "isolated.sqlite3").exists()


class _FakeResponse:
    def __init__(self, payload, status=200):
        self._payload, self.status_code = payload, status
        self.is_success = 200 <= status < 300
        self.text = str(payload)

    def json(self):
        return self._payload


class _FakeAsyncClient:
    calls: list[str] = []

    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def post(self, url, **_kwargs):
        _FakeAsyncClient.calls.append(url)
        return _FakeResponse({"status": "outside_coverage", "coverage": {"status": "outside_india", "reason": "outside India"}})


def test_outside_india_is_returned_without_enrichment_or_saving(client, monkeypatch) -> None:
    _FakeAsyncClient.calls = []
    monkeypatch.setattr(parcels.httpx, "AsyncClient", _FakeAsyncClient)
    response = client.post("/api/v1/parcels/analyze", json={
        "polygon": POLYGON, "address": "Colombo", "analysis_date_from": "2025-01-01", "analysis_date_to": "2026-01-01"})
    assert response.status_code == 200
    assert response.json()["status"] == "outside_coverage"
    assert len(_FakeAsyncClient.calls) == 1 and _FakeAsyncClient.calls[0].endswith("/internal/analysis/build")
    assert client.get("/api/v1/parcels").json()["reports"] == []


class _FailingPipelineClient(_FakeAsyncClient):
    async def post(self, url, **_kwargs):
        return _FakeResponse({"detail": "The India coverage boundary is not installed. Run: terrascope.cmd fetch-data"}, status=503)


def test_pipeline_errors_are_relayed_with_their_status(client, monkeypatch) -> None:
    """_downstream_error (J-08): a 503 from data-pipeline stays a 503 with its message, not a NameError/500."""
    monkeypatch.setattr(parcels.httpx, "AsyncClient", _FailingPipelineClient)
    response = client.post("/api/v1/parcels/analyze", json={
        "polygon": POLYGON, "address": "Kadapa", "analysis_date_from": "2025-01-01", "analysis_date_to": "2026-01-01"})
    assert response.status_code == 503
    assert "data-pipeline" in response.json()["detail"] and "fetch-data" in response.json()["detail"]
