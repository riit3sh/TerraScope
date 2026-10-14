"""Downstream service addressing must work outside Docker and fail legibly."""

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "backend-api"), str(ROOT / "backend-api" / "src")]

from routers import parcels  # noqa: E402

POLYGON = {
    "type": "Polygon",
    "coordinates": [[[73.85, 18.515], [73.8515, 18.515], [73.8515, 18.5165], [73.85, 18.5165], [73.85, 18.515]]],
}


def test_defaults_resolve_without_compose_dns(monkeypatch: pytest.MonkeyPatch) -> None:
    # Compose sets both URLs explicitly; a bare run on Windows must not fall back
    # to the Compose-only hostnames, which fail with [Errno 11001] getaddrinfo.
    monkeypatch.delenv("DATA_PIPELINE_URL", raising=False)
    monkeypatch.delenv("ML_MODELS_URL", raising=False)
    assert parcels.data_pipeline_url() == "http://127.0.0.1:8001"
    assert parcels.ml_models_url() == "http://127.0.0.1:8002"


def test_unreachable_service_error_names_the_service_and_host(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("DATA_PIPELINE_URL", "http://no-such-service.invalid:8001")
    from terrascope_backend_api.main import app

    response = TestClient(app).post(
        "/api/v1/parcels/analyze",
        json={"polygon": POLYGON, "analysis_date_from": "2025-01-01", "analysis_date_to": "2025-06-30"},
    )
    assert response.status_code == 502
    detail = response.json()["detail"]
    assert "data-pipeline" in detail
    assert "no-such-service.invalid:8001" in detail
