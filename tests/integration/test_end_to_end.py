"""Black-box integration tests against the running data-pipeline and ml-models services.

The tests never write to the user's saved reports: they start their own backend-api
on a spare port with a temporary BACKEND_STORE_PATH, which is deleted afterwards.
Set TERRASCOPE_TEST_BACKEND_URL to point at an already-isolated backend instead.

    terrascope.cmd start      (data-pipeline :8001 and ml-models :8002 must be up)
    pytest tests/integration -v
"""

from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

import httpx
import pytest
from jsonschema import Draft202012Validator, FormatChecker


ROOT = Path(__file__).resolve().parents[2]
SCHEMA_PATH = ROOT / "docs" / "schema" / "parcel_schema.json"
BACKEND_URL = os.getenv("TERRASCOPE_TEST_BACKEND_URL", "")
SAMPLE_RAG_PARCEL_IDS = {"parcel-pune-001", "parcel-pune-002"}

# TerraScope covers Tamil Nadu only: Vellore city, Chennai (Velachery) and Madurai.
POLYGONS = [
    {
        "type": "Polygon",
        "coordinates": [[[79.1320, 12.9200], [79.1329, 12.9200], [79.1329, 12.9209], [79.1320, 12.9209], [79.1320, 12.9200]]],
    },
    {
        "type": "Polygon",
        "coordinates": [[[80.2120, 12.9856], [80.2128, 12.9856], [80.2128, 12.9863], [80.2120, 12.9863], [80.2120, 12.9856]]],
    },
    {
        "type": "Polygon",
        "coordinates": [[[78.1190, 9.9240], [78.1200, 9.9240], [78.1200, 9.9250], [78.1190, 9.9250], [78.1190, 9.9240]]],
    },
]
# Colombo, Sri Lanka: outside India, so nothing may be collected or saved.
OUTSIDE_POLYGON = {
    "type": "Polygon",
    "coordinates": [[[79.8600, 6.9300], [79.8610, 6.9300], [79.8610, 6.9310], [79.8600, 6.9310], [79.8600, 6.9300]]],
}
# Pune, Maharashtra: inside India, but no regional OSM cache is installed for it.
NO_REGION_POLYGON = {
    "type": "Polygon",
    "coordinates": [[[73.7950, 18.5900], [73.7980, 18.5900], [73.7980, 18.5925], [73.7950, 18.5925], [73.7950, 18.5900]]],
}

EVALUATIONS = [
    {"profile": "homebuyer", "property_type": "residential", "investment_horizon": "1_to_3y", "weights": {"growth_pct": 20, "legal_safety_pct": 35, "accessibility_pct": 25, "flood_safety_pct": 20}, "preferences": {"road_importance": "medium", "school_importance": "high", "max_road_distance_m": 3000, "max_school_distance_m": 5000, "rera_requirement": "important"}},
    {"profile": "developer", "property_type": "commercial", "investment_horizon": "3_to_5y", "weights": {"growth_pct": 40, "legal_safety_pct": 20, "accessibility_pct": 30, "flood_safety_pct": 10}, "preferences": {"road_importance": "high", "school_importance": "low", "max_road_distance_m": 5000, "max_school_distance_m": 8000, "rera_requirement": "strict"}},
    {"profile": "conservative", "property_type": "residential", "investment_horizon": "5_to_10y", "weights": {"growth_pct": 10, "legal_safety_pct": 40, "accessibility_pct": 20, "flood_safety_pct": 30}, "preferences": {"road_importance": "medium", "school_importance": "medium", "max_road_distance_m": 3000, "max_school_distance_m": 5000, "rera_requirement": "strict"}},
]


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


@pytest.fixture(scope="session")
def client() -> httpx.Client:
    """A backend-api of our own with a throwaway database, wired to the live services."""
    process = None
    tmp = tempfile.TemporaryDirectory(prefix="terrascope-it-", ignore_cleanup_errors=True)
    base_url = BACKEND_URL
    if not base_url:
        port = _free_port()
        env = {
            **os.environ,
            "BACKEND_STORE_PATH": str(Path(tmp.name) / "integration.sqlite3"),
            "PYTHONPATH": os.pathsep.join([str(ROOT), str(ROOT / "backend-api"), str(ROOT / "backend-api" / "src")]),
        }
        process = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "terrascope_backend_api.main:app", "--host", "127.0.0.1",
             "--port", str(port), "--log-level", "warning"],
            cwd=str(ROOT), env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        base_url = f"http://127.0.0.1:{port}"
    client = httpx.Client(base_url=base_url, timeout=httpx.Timeout(120.0, connect=10.0))
    try:
        for _ in range(60):
            try:
                if client.get("/api/v1/health").status_code == 200:
                    break
            except httpx.HTTPError:
                pass
            time.sleep(0.5)
        else:
            pytest.skip(f"Isolated test backend did not start at {base_url}")
        try:
            pipeline = httpx.get("http://127.0.0.1:8001/health", timeout=5).status_code
        except httpx.HTTPError:
            pipeline = None
        if pipeline != 200:
            pytest.skip("data-pipeline is not running on :8001 (run terrascope.cmd start)")
        yield client
    finally:
        client.close()
        if process is not None:
            # On Windows a venv python.exe is a launcher that starts the real interpreter as a
            # child; terminating only the launcher would leave uvicorn holding the test database.
            if os.name == "nt":
                subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"], capture_output=True, check=False)
            else:
                process.terminate()
            process.wait(timeout=20)
        tmp.cleanup()


def validate_snapshot(snapshot: dict[str, Any]) -> None:
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    errors = sorted(Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(snapshot), key=lambda e: list(e.path))
    assert not errors, "; ".join(error.message for error in errors[:5])


def assert_polygon(geometry: dict[str, Any]) -> None:
    assert geometry.get("type") == "Polygon"
    rings = geometry.get("coordinates")
    assert isinstance(rings, list) and rings
    for ring in rings:
        assert len(ring) >= 4
        assert ring[0] == ring[-1]
        assert all(isinstance(position, list) and len(position) >= 2 for position in ring)


def analyse(client: httpx.Client, polygon: dict[str, Any]) -> dict[str, Any]:
    response = client.post("/api/v1/parcels/analyze", json={"polygon": polygon, "address": "Tamil Nadu", "analysis_date_from": "2023-01-01", "analysis_date_to": "2025-01-01"}, timeout=120.0)
    assert response.status_code == 200, response.text
    body = response.json()
    snapshot = body["evidence_snapshot"]
    assert body["analysis_snapshot_id"] == snapshot["metadata"]["analysis_snapshot_id"]
    validate_snapshot(snapshot)
    assert_polygon(snapshot["geometry"])
    metrics = snapshot["geometry_metadata"]
    assert metrics["area_m2"] and metrics["area_m2"] > 0
    assert metrics["perimeter_m"] and metrics["perimeter_m"] > 0
    return snapshot


def evaluate(client: httpx.Client, snapshot: dict[str, Any], settings: dict[str, Any]) -> dict[str, Any]:
    response = client.post(f"/api/v1/parcels/{snapshot['parcel_id']}/evaluate", json={"analysis_snapshot_id": snapshot["metadata"]["analysis_snapshot_id"], **settings}, timeout=20.0)
    assert response.status_code == 200, response.text
    result = response.json()
    # INSUFFICIENT_EVIDENCE is a valid answer since verdicts are withheld when evidence is thin (067d541).
    assert result["verdict"]["recommendation"] in {"BUY", "WAIT", "AVOID", "INSUFFICIENT_EVIDENCE"}
    return result


def test_full_pipeline_for_three_tamil_nadu_polygons(client: httpx.Client) -> None:
    snapshots = [analyse(client, polygon) for polygon in POLYGONS]
    for snapshot, settings in zip(snapshots, EVALUATIONS):
        result = evaluate(client, snapshot, settings)
        if snapshot["parcel_id"] in SAMPLE_RAG_PARCEL_IDS:
            assert result["verdict"]["citations"], f"Expected sample RAG citations for {snapshot['parcel_id']}"


def test_re_evaluation_reuses_immutable_evidence(client: httpx.Client) -> None:
    snapshot = analyse(client, POLYGONS[0])
    snapshot_id = snapshot["metadata"]["analysis_snapshot_id"]
    first = evaluate(client, snapshot, EVALUATIONS[0])
    second_settings = {**EVALUATIONS[0], "weights": {"growth_pct": 45, "legal_safety_pct": 20, "accessibility_pct": 20, "flood_safety_pct": 15}}
    second = evaluate(client, snapshot, second_settings)
    assert first["metadata"]["analysis_snapshot_id"] == snapshot_id
    assert second["metadata"]["analysis_snapshot_id"] == snapshot_id
    stored = client.get(f"/api/v1/analysis/{snapshot_id}", timeout=10.0)
    assert stored.status_code == 200
    assert stored.json() == snapshot


def test_changed_polygon_invalidates_previous_snapshot(client: httpx.Client) -> None:
    original = analyse(client, POLYGONS[1])
    changed_polygon = {"type": "Polygon", "coordinates": [[[80.2120, 12.9856], [80.2131, 12.9856], [80.2131, 12.9863], [80.2120, 12.9863], [80.2120, 12.9856]]]}
    changed = analyse(client, changed_polygon)
    assert changed["metadata"]["analysis_snapshot_id"] != original["metadata"]["analysis_snapshot_id"]
    assert changed["geometry"] != original["geometry"]


def test_uploaded_text_becomes_retrievable_parcel_evidence(client: httpx.Client) -> None:
    snapshot = analyse(client, POLYGONS[2])
    parcel_id = snapshot["parcel_id"]
    fixture = Path(__file__).parent / "fixtures" / "title_evidence.txt"
    with fixture.open("rb") as handle:
        response = client.post(f"/api/v1/parcels/{parcel_id}/documents", files={"file": (fixture.name, handle, "text/plain")}, timeout=20.0)
    assert response.status_code == 200, response.text
    assert response.json()["text_indexed"] is True
    parcel = client.get(f"/api/v1/parcels/{parcel_id}", timeout=10.0)
    assert parcel.status_code == 200
    uploaded = parcel.json()["uploaded_documents"]
    assert any(item["source_reference"] == fixture.name and item["source_type"] == "user_upload" for item in uploaded)
    evaluated = evaluate(client, snapshot, EVALUATIONS[0])
    ledger = [item for item in evaluated["evidence"] if item["source_type"] == "user_upload"]
    assert [item["source_reference"] for item in ledger] == [fixture.name]
    assert all(item["freshness"] == "user_upload" for item in ledger)


def test_parcel_outside_india_is_refused_without_a_report(client: httpx.Client) -> None:
    before = len(client.get("/api/v1/parcels").json()["reports"])
    response = client.post("/api/v1/parcels/analyze", json={
        "polygon": OUTSIDE_POLYGON, "address": "Colombo, Sri Lanka",
        "analysis_date_from": "2023-01-01", "analysis_date_to": "2025-01-01",
    }, timeout=60.0)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "outside_coverage"
    assert body["coverage"]["status"] == "outside_india"
    assert "evidence_snapshot" not in body
    assert len(client.get("/api/v1/parcels").json()["reports"]) == before


def test_indian_parcel_without_regional_data_is_analysed(client: httpx.Client) -> None:
    """Missing regional OSM data must not block the India-wide collectors."""
    snapshot = analyse(client, NO_REGION_POLYGON)
    assert snapshot["coverage"]["status"] == "inside"
    assert snapshot["coverage"]["regional_data"] is None
    assert snapshot["infrastructure"]["nearest_road_distance_m"] is None
    osm_row = next(row for row in snapshot["evidence"] if row["source_type"] == "openstreetmap")
    assert "fetch-data" in osm_row["summary"]
    river = next(c for c in snapshot["flood_indicators"]["components"] if c["mechanism"] == "river_flooding")
    assert river["status"] in {"assessed", "partial", "not_modelled", "unavailable"}
    assert snapshot["risk"]["flood_risk_score"] is None
