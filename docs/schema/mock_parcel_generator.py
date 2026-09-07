"""Generate local-only fake TerraScope ParcelRecord data."""

from __future__ import annotations

import json
import random
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from faker import Faker


OUTPUT_PATH = Path(__file__).with_name("mock_parcels.json")
RNG = random.Random(20260907)
FAKE = Faker("en_IN")
Faker.seed(20260907)

STATES = ["Karnataka", "Maharashtra", "Telangana", "Tamil Nadu", "Kerala"]
ROAD_TYPES = ["highway", "state_highway", "district_road", "village_road"]
CHANGE_TYPES = ["construction_growth", "vegetation_loss", "no_change"]


def maybe(value: Any, missing_rate: float = 0.12) -> Any:
    return None if RNG.random() < missing_rate else value


def iso_date(days_ago: int) -> str:
    return (date.today() - timedelta(days=days_ago)).isoformat()


def iso_datetime(days_ago: int) -> str:
    moment = datetime.now(timezone.utc) - timedelta(days=days_ago)
    return moment.replace(microsecond=0).isoformat().replace("+00:00", "Z")


def polygon(latitude: float, longitude: float) -> dict[str, Any]:
    delta = 0.0012
    ring = [
        [longitude, latitude],
        [longitude + delta, latitude],
        [longitude + delta, latitude + delta],
        [longitude, latitude + delta],
        [longitude, latitude],
    ]
    return {"type": "Polygon", "coordinates": [ring]}


def trend(start_days_ago: int, count: int, base: float, slope: float) -> list[dict[str, Any]]:
    return [
        {
            "date": iso_date(start_days_ago - (index * 30)),
            "value": round(max(-1.0, min(1.0, base + (index * slope) + RNG.uniform(-0.04, 0.04))), 3),
        }
        for index in range(count)
    ]


def make_parcel(index: int) -> dict[str, Any]:
    latitude = round(RNG.uniform(8.5, 19.2), 6)
    longitude = round(RNG.uniform(74.0, 80.4), 6)
    # Keep the source data deliberately varied so downstream null handling is exercised.
    has_rera = RNG.random() > 0.28
    has_satellite = RNG.random() > 0.18
    recommendation = RNG.choices(["BUY", "WAIT", "AVOID"], weights=[4, 4, 2])[0]
    change_type = RNG.choice(CHANGE_TYPES)
    growth_score = RNG.randint(35, 94)
    legal_score = RNG.randint(25, 96)
    accessibility_score = RNG.randint(30, 95)
    flood_safety_score = RNG.randint(25, 95)
    weights = {"growth_pct": 30, "legal_safety_pct": 30, "accessibility_pct": 20, "flood_safety_pct": 20}
    area_m2 = round(RNG.uniform(1800, 24000), 2)

    return {
        "parcel_id": str(uuid4()),
        "location": {
            "latitude": latitude,
            "longitude": longitude,
            "address": maybe(FAKE.street_address()),
            "village": FAKE.city_suffix() + " Village",
            "district": FAKE.city(),
            "state": RNG.choice(STATES),
            "pincode": str(RNG.randint(500000, 699999)),
        },
        "geometry": maybe(polygon(latitude, longitude), 0.08),
        "geometry_metadata": {
            "area_m2": area_m2,
            "area_acres": round(area_m2 / 4046.8564224, 3),
            "perimeter_m": round(RNG.uniform(180, 700), 2),
            "boundary_source": RNG.choice(["user_drawn", "imported", "estimated", "unknown"]),
            "boundary_verified": maybe(RNG.choice([True, False]), 0.1),
        },
        "land_records": {
            "survey_number": maybe(f"SY-{RNG.randint(100, 999)}/{RNG.randint(1, 12)}"),
            "ownership_type": RNG.choice(["freehold", "freehold", "leasehold", "disputed", "unknown"]),
            "title_clear": maybe(legal_score >= 55),
            "encumbrance_flag": maybe(legal_score < 50, 0.08),
            "source_document_ids": [f"DOC-{index:03d}-{n}" for n in range(1, RNG.randint(1, 4))],
        },
        "rera": {
            "is_rera_project": has_rera,
            "rera_registration_number": f"PRM/{RNG.randint(2018, 2025)}/{RNG.randint(10000, 99999)}" if has_rera else None,
            "promoter_name": FAKE.company() if has_rera else None,
            "registered_completion_date": (date.today() + timedelta(days=RNG.randint(180, 1800))).isoformat() if has_rera else None,
            "source_url": f"https://rera.example.test/project/{index}" if has_rera else None,
        },
        "satellite": {
            "imagery_dates": [iso_date(days) for days in [30, 90, 150, 210]] if has_satellite else [],
            "ndvi_trend": trend(30, 4, 0.35, -0.02) if has_satellite else [],
            "ndbi_trend": trend(30, 4, 0.12, 0.04) if has_satellite else [],
            "change_detected": RNG.choice([True, False]) if has_satellite else None,
            "change_type": change_type if has_satellite else "insufficient_evidence",
            "change_confidence": round(RNG.uniform(0.58, 0.96), 2) if has_satellite else None,
        },
        "infrastructure": {
            "nearest_road_distance_m": round(RNG.uniform(25, 2500), 1),
            "nearest_road_type": RNG.choice(ROAD_TYPES),
            "nearest_school_distance_m": round(RNG.uniform(250, 6500), 1),
        },
        "risk": {
            "flood_risk_score": 100 - flood_safety_score,
            "flood_risk_basis": "Local elevation model and historical flood-zone overlay.",
            "elevation_m": round(RNG.uniform(8, 920), 1),
            "legal_risk_score": 100 - legal_score,
            "accessibility_score": accessibility_score,
        },
        "opportunity": {
            "growth_score": growth_score,
            "infra_growth_trend": RNG.choice(["rising", "stable", "declining"]),
        },
        "evaluation": {
            "profile": RNG.choice(["homebuyer", "developer", "investor", "conservative", "custom"]),
            "property_type": RNG.choice(["residential", "commercial", "industrial", "mixed_use"]),
            "investment_horizon": RNG.choice(["under_1y", "1_to_3y", "3_to_5y", "5_to_10y", "10_plus_y"]),
            "weights": weights,
            "preferences": {
                "road_importance": RNG.choice(["low", "medium", "high"]),
                "school_importance": RNG.choice(["low", "medium", "high"]),
                "max_road_distance_m": round(RNG.uniform(500, 3000), 1),
                "max_school_distance_m": round(RNG.uniform(1000, 6000), 1),
                "rera_requirement": RNG.choice(["strict", "important", "informational"]),
            },
        },
        "score_breakdown": {
            "legal_safety_score": legal_score,
            "accessibility_score": accessibility_score,
            "flood_safety_score": flood_safety_score,
            "growth_score": growth_score,
            "weighted_contributions": [
                {"factor": "growth", "contribution": round(growth_score * 0.30, 2)},
                {"factor": "legal_safety", "contribution": round(legal_score * 0.30, 2)},
                {"factor": "accessibility", "contribution": round(accessibility_score * 0.20, 2)},
                {"factor": "flood_safety", "contribution": round(flood_safety_score * 0.20, 2)},
            ],
        },
        "evidence": [
            {
                "evidence_id": f"EVD-{index:03d}-LAND",
                "source_type": "land_record",
                "source_reference": f"DOC-{index:03d}-1",
                "title": "Land record extract",
                "observed_at": iso_datetime(12),
                "freshness": "cached",
                "summary": "Seed land-record evidence for schema and UI development.",
            },
            {
                "evidence_id": f"EVD-{index:03d}-SAT",
                "source_type": "satellite",
                "source_reference": f"sentinelhub://parcel/{index}",
                "title": "Satellite imagery summary",
                "observed_at": iso_datetime(30),
                "freshness": "derived" if has_satellite else "seed_data",
                "summary": "Satellite evidence is included when a history is available." if has_satellite else None,
            },
        ],
        "verdict": {
            "recommendation": recommendation,
            "confidence": round(RNG.uniform(0.55, 0.96), 2),
            "reasoning_summary": f"{recommendation.title()} based on legal safety, access, flood safety, and growth signals.",
            "citations": [
                {
                    "claim": "Land-record and risk signals support the current assessment.",
                    "source_type": "land_record",
                    "source_reference": f"DOC-{index:03d}-1",
                }
            ],
        },
        "metadata": {
            "last_updated": iso_datetime(1),
            "data_completeness_pct": round(RNG.uniform(68, 99) if has_satellite else RNG.uniform(45, 75), 1),
            "analysis_date_from": iso_date(240),
            "analysis_date_to": iso_date(30),
            "analysis_snapshot_id": f"SNAP-{date.today().strftime('%Y%m%d')}-{index:03d}",
        },
    }


def main() -> None:
    parcels = [make_parcel(index) for index in range(1, 51)]
    OUTPUT_PATH.write_text(json.dumps(parcels, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {len(parcels)} mock ParcelRecord objects to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
