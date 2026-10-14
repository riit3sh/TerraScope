"""Seed the backend store with one schema-valid snapshot for UI smoke checks.

This exercises the report UI without the data-pipeline/PostGIS stack. The
snapshot is a fixture, not collected evidence: it is stamped as such in its
evidence ledger so nobody mistakes a UI check for a data check.
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "backend-api")]

from jsonschema import Draft202012Validator, FormatChecker  # noqa: E402

from routers.store import init_store, save_document, save_evaluation, save_snapshot  # noqa: E402

NOW = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
# A ~1.1 ha block just west of central Pune, inside the synthetic model's coverage.
POLYGON = {
    "type": "Polygon",
    "coordinates": [[
        [73.8500, 18.5150], [73.8515, 18.5150], [73.8515, 18.5165],
        [73.8500, 18.5165], [73.8500, 18.5150],
    ]],
}


def build_snapshot() -> dict:
    snapshot_id, parcel_id = str(uuid4()), str(uuid4())
    return {
        "parcel_id": parcel_id,
        "location": {
            "latitude": 18.51575, "longitude": 73.85075,
            "address": "[UI DEMO FIXTURE] Erandwane, Pune, Maharashtra, 411004, India",
            "village": "Erandwane", "district": "Pune", "state": "Maharashtra", "pincode": "411004",
        },
        "geometry": POLYGON,
        "geometry_metadata": {
            "area_m2": 11122.5, "area_acres": 2.748, "perimeter_m": 422.4,
            "boundary_source": "user_drawn", "boundary_verified": None,
        },
        "land_records": None,
        "rera": {
            "is_rera_project": None, "rera_registration_number": None, "promoter_name": None,
            "registered_completion_date": None, "source_url": None,
        },
        "satellite": {
            "imagery_dates": ["2024-02-11", "2024-08-17", "2025-03-04", "2025-09-21"],
            "ndvi_trend": [
                {"date": "2024-02-11", "value": 0.412}, {"date": "2024-08-17", "value": 0.388},
                {"date": "2025-03-04", "value": 0.331}, {"date": "2025-09-21", "value": 0.284},
            ],
            "ndbi_trend": [
                {"date": "2024-02-11", "value": -0.104}, {"date": "2024-08-17", "value": -0.041},
                {"date": "2025-03-04", "value": 0.037}, {"date": "2025-09-21", "value": 0.092},
            ],
            "change_detected": True, "change_type": "construction_growth", "change_confidence": 0.324,
        },
        "infrastructure": {
            "nearest_road_distance_m": 182.4, "nearest_road_type": "secondary",
            "nearest_school_distance_m": 640.2,
            "nearest_road_lat": 18.51492, "nearest_road_lon": 73.85201,
            "nearest_school_lat": 18.51958, "nearest_school_lon": 73.84812,
        },
        "risk": {
            "flood_risk_score": 28.0,
            "flood_risk_basis": "FIXTURE value, not measured: centroid 9.4 m above a baseline elevation.",
            "elevation_m": 559.4, "legal_risk_score": None, "accessibility_score": None,
        },
        "opportunity": {"growth_score": 62.0, "infra_growth_trend": "rising"},
        "evidence": [
            {
                "evidence_id": f"{snapshot_id}:fixture", "source_type": "derived",
                "source_reference": "ui_demo_fixture", "title": "UI demo fixture (not collected evidence)",
                "observed_at": NOW, "freshness": "derived",
                "summary": "Seeded by scripts/seed_ui_demo.py to exercise the report UI without the collection stack.",
            },
            {
                "evidence_id": f"{snapshot_id}:osm", "source_type": "openstreetmap",
                "source_reference": "ui_demo_fixture (not fetched from Overpass)", "title": "FIXTURE: nearby infrastructure",
                "observed_at": NOW, "freshness": "seed_data",
                "summary": "Hand-written fixture values (road 182 m, school 640 m); nothing was measured.",
            },
            {
                "evidence_id": f"{snapshot_id}:elevation", "source_type": "open_elevation",
                "source_reference": "ui_demo_fixture (not fetched from Open-Elevation)", "title": "FIXTURE: elevation",
                "observed_at": NOW, "freshness": "seed_data",
                "summary": "Hand-written fixture value (559.4 m); nothing was measured.",
            },
            {
                "evidence_id": f"{snapshot_id}:rera", "source_type": "maharera_seed",
                "source_reference": "ui_demo_fixture (no RERA lookup performed)", "title": "FIXTURE: RERA status",
                "observed_at": NOW, "freshness": "seed_data",
                "summary": "No RERA lookup was performed for this fixture, so RERA status is unknown.",
            },
            {
                "evidence_id": f"{snapshot_id}:satellite", "source_type": "satellite",
                "source_reference": "ui_demo_fixture (not NASA AppEEARS imagery)", "title": "FIXTURE: invented satellite series",
                "observed_at": NOW, "freshness": "seed_data",
                "summary": "4 INVENTED NDVI/NDBI points to exercise the chart; this is not imagery.",
            },
        ],
        "verdict": None,
        "metadata": {
            "last_updated": NOW, "data_completeness_pct": 77.8,
            "analysis_date_from": "2024-01-01", "analysis_date_to": "2026-09-26",
            "analysis_snapshot_id": snapshot_id,
        },
    }


def main() -> None:
    schema = json.loads((ROOT / "docs" / "schema" / "parcel_schema.json").read_text(encoding="utf-8"))
    snapshot = build_snapshot()
    errors = sorted(
        Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(snapshot),
        key=lambda error: list(error.path),
    )
    if errors:
        raise SystemExit("seed snapshot is not schema-valid: " + "; ".join(e.message for e in errors[:5]))

    init_store()
    save_snapshot(snapshot)
    parcel_id = snapshot["parcel_id"]
    save_document(parcel_id, "title_extract.txt", "text/plain", 241,
                  "Survey No. 118/2A, Pune District. Title record should be reviewed against the current certified extract.")

    sys.path.insert(0, str(ROOT / "ml-models"))
    from pipeline import evaluate_snapshot

    evaluation = {
        "profile": "homebuyer", "property_type": "residential", "investment_horizon": "1_to_3y",
        "weights": {"growth_pct": 20, "legal_safety_pct": 35, "accessibility_pct": 25, "flood_safety_pct": 20},
        "preferences": {"road_importance": "medium", "school_importance": "high",
                        "max_road_distance_m": 3000, "max_school_distance_m": 5000,
                        "rera_requirement": "important"},
    }
    request_snapshot = dict(snapshot)
    request_snapshot["uploaded_documents"] = [{
        "text": "Survey No. 118/2A, Pune District. Title record should be reviewed.",
        "source_type": "user_upload", "source_reference": "title_extract.txt", "parcel_id": parcel_id,
    }]
    evaluated = evaluate_snapshot(request_snapshot, evaluation)
    save_evaluation(parcel_id, snapshot["metadata"]["analysis_snapshot_id"], evaluated)

    print(json.dumps({
        "store": os.getenv("BACKEND_STORE_PATH"),
        "parcel_id": parcel_id,
        "snapshot_id": snapshot["metadata"]["analysis_snapshot_id"],
        "verdict": evaluated["verdict"]["recommendation"],
        "composite": evaluated["score_breakdown"]["composite_score"],
        "upload_rows": [i["source_reference"] for i in evaluated["evidence"] if i["source_type"] == "user_upload"],
    }, indent=2))


if __name__ == "__main__":
    main()
