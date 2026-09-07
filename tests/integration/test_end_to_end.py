"""Black-box integration tests for a running local Compose stack.

Run after ``docker-compose up --build`` with:
    pytest tests/integration/test_end_to_end.py -v
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx
import pytest
from jsonschema import Draft202012Validator, FormatChecker


ROOT = Path(__file__).resolve().parents[2]
SCHEMA_PATH = ROOT / "docs" / "schema" / "parcel_schema.json"
BACKEND_URL = "http://localhost:8000"
SAMPLE_RAG_PARCEL_IDS = {"parcel-pune-001", "parcel-pune-002"}

POLYGONS = [
    {
        "type": "Polygon",
        "coordinates": [[[73.7950, 18.5900], [73.7980, 18.5900], [73.7980, 18.5925], [73.7950, 18.5925], [73.7950, 18.5900]]],
    },
    {
        "type": "Polygon",
        "coordinates": [[[73.7750, 18.4750], [73.7790, 18.4750], [73.7790, 18.4780], [73.7750, 18.4780], [73.7750, 18.4750]]],
    },
    {
        "type": "Polygon",
        "coordinates": [[[73.6900, 18.5250], [73.6940, 18.5250], [73.6940, 18.5280], [73.6900, 18.5280], [73.6900, 18.5250]]],
    },
]

EVALUATIONS = [
    {"profile": "homebuyer", "property_type": "residential", "investment_horizon": "1_to_3y", "weights": {"growth_pct": 20, "legal_safety_pct": 35, "accessibility_pct": 25, "flood_safety_pct": 20}, "preferences": {"road_importance": "medium", "school_importance": "high", "max_road_distance_m": 3000, "max_school_distance_m": 5000, "rera_requirement": "important"}},
    {"profile": "developer", "property_type": "commercial", "investment_horizon": "3_to_5y", "weights": {"growth_pct": 40, "legal_safety_pct": 20, "accessibility_pct": 30, "flood_safety_pct": 10}, "preferences": {"road_importance": "high", "school_importance": "low", "max_road_distance_m": 5000, "max_school_distance_m": 8000, "rera_requirement": "strict"}},
    {"profile": "conservative", "property_type": "residential", "investment_horizon": "5_to_10y", "weights": {"growth_pct": 10, "legal_safety_pct": 40, "accessibility_pct": 20, "flood_safety_pct": 30}, "preferences": {"road_importance": "medium", "school_importance": "medium", "max_road_distance_m": 3000, "max_school_distance_m": 5000, "rera_requirement": "strict"}},
]


@pytest.fixture(scope="session")
def client() -> httpx.Client:
    client = httpx.Client(base_url=BACKEND_URL, timeout=httpx.Timeout(120.0, connect=10.0))
    try:
        response = client.get("/api/v1/health")
    except httpx.HTTPError as error:
        pytest.skip(f"Compose backend is not running at {BACKEND_URL}: {error}")
    if response.status_code != 200:
        pytest.skip(f"Compose backend is unhealthy: HTTP {response.status_code}")
    yield client
    client.close()


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
    response = client.post("/api/v1/parcels/analyze", json={"polygon": polygon, "address": "Pune, Maharashtra", "analysis_date_from": "2023-01-01", "analysis_date_to": "2025-01-01"}, timeout=120.0)
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
    assert result["verdict"]["recommendation"] in {"BUY", "WAIT", "AVOID"}
    return result


def test_full_pipeline_for_three_real_pune_polygons(client: httpx.Client) -> None:
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
    changed_polygon = {"type": "Polygon", "coordinates": [[[73.7750, 18.4750], [73.7800, 18.4750], [73.7800, 18.4790], [73.7750, 18.4790], [73.7750, 18.4750]]]}
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
