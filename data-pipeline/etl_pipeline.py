"""Blocking evidence collection for one TerraScope parcel analysis."""

from __future__ import annotations

import json
import os
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

import pandas as pd
from jsonschema import Draft202012Validator, FormatChecker

from connectors.elevation_dem import ElevationClient
from connectors.osm_infrastructure import InfrastructureClient
from connectors.rera_ingest import load_rera_seed_dataset, match_parcel_to_rera
from connectors.satellite_provider import get_satellite_client



def _schema_path() -> Path:
    candidates = [Path(__file__).resolve().parent, Path(__file__).resolve().parents[1]]
    for root in candidates:
        candidate = root / "docs" / "schema" / "parcel_schema.json"
        if candidate.exists():
            return candidate
    return candidates[0] / "docs" / "schema" / "parcel_schema.json"


SCHEMA_PATH = _schema_path()


class EvidenceSnapshotValidationError(ValueError):
    """Raised when collected evidence does not satisfy the shared schema."""


def _date_only(value: date | datetime | str) -> str:
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return date.fromisoformat(str(value)[:10]).isoformat()


def _location_from_context(
    latitude: float,
    longitude: float,
    context: dict[str, Any] | None,
    requested_address: str | None,
) -> dict[str, Any]:
    address_parts = context.get("address", {}) if isinstance(context, dict) else {}
    if not isinstance(address_parts, dict):
        address_parts = {}
    return {
        "latitude": latitude,
        "longitude": longitude,
        "address": (context or {}).get("display_name") or requested_address,
        "village": address_parts.get("village") or address_parts.get("town") or address_parts.get("city_district"),
        "district": address_parts.get("state_district") or address_parts.get("district"),
        "state": address_parts.get("state"),
        "pincode": address_parts.get("postcode"),
    }


def _satellite_facts(series: list[dict[str, Any]]) -> dict[str, Any]:
    imagery_dates = [record["date"] for record in series]
    ndvi_trend = [{"date": record["date"], "value": record["ndvi"]} for record in series]
    ndbi_trend = [{"date": record["date"], "value": record["ndbi"]} for record in series]
    usable = [record for record in series if record.get("ndvi") is not None and record.get("ndbi") is not None]
    if len(usable) < 2:
        return {
            "imagery_dates": imagery_dates,
            "ndvi_trend": ndvi_trend,
            "ndbi_trend": ndbi_trend,
            "change_detected": None,
            "change_type": "insufficient_evidence",
            "change_confidence": None,
        }

    first, last = usable[0], usable[-1]
    ndvi_delta = last["ndvi"] - first["ndvi"]
    ndbi_delta = last["ndbi"] - first["ndbi"]
    if ndbi_delta > 0.05:
        change_type = "construction_growth"
    elif ndvi_delta < -0.05:
        change_type = "vegetation_loss"
    else:
        change_type = "no_change"
    confidence = min(1.0, max(0.0, abs(ndvi_delta) + abs(ndbi_delta)))
    return {
        "imagery_dates": imagery_dates,
        "ndvi_trend": ndvi_trend,
        "ndbi_trend": ndbi_trend,
        "change_detected": change_type != "no_change",
        "change_type": change_type,
        "change_confidence": round(confidence, 3),
    }


def _load_rera_or_empty() -> pd.DataFrame:
    seed_path = Path(os.getenv("RERA_SEED_PATH", str(Path(__file__).parent / "data" / "raw" / "maharera_seed.csv")))
    if not seed_path.exists():
        return pd.DataFrame({"district": pd.Series(dtype="string")})
    return load_rera_seed_dataset(seed_path)


def _validate_snapshot(snapshot: dict[str, Any]) -> None:
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    errors = sorted(validator.iter_errors(snapshot), key=lambda error: list(error.path))
    if errors:
        details = "; ".join(
            f"{'.'.join(str(part) for part in error.path) or 'root'}: {error.message}" for error in errors[:5]
        )
        raise EvidenceSnapshotValidationError(f"Evidence snapshot failed schema validation: {details}")


def build_evidence_snapshot(
    geojson_polygon: dict[str, Any],
    date_from: date | datetime | str,
    date_to: date | datetime | str,
    address: str | None = None,
) -> dict[str, Any]:
    """Collect and validate one immutable, investor-neutral evidence snapshot."""
    # The connector performs structural validation before any external request.
    InfrastructureClient._validate_polygon(geojson_polygon)
    start = _date_only(date_from)
    end = _date_only(date_to)
    if start > end:
        raise ValueError("date_from must be on or before date_to.")

    infrastructure_client = InfrastructureClient()
    satellite_client = get_satellite_client()
    elevation_client = ElevationClient()
    latitude, longitude = elevation_client.polygon_centroid(geojson_polygon)
    metrics = infrastructure_client.polygon_metrics(geojson_polygon)

    if address:
        geocoded = infrastructure_client.geocode_address(address)
        location_context = geocoded[0] if geocoded else None
    else:
        location_context = infrastructure_client.reverse_geocode(latitude, longitude)
    location = _location_from_context(latitude, longitude, location_context, address)

    change_series = satellite_client.get_change_series(geojson_polygon, start, end)
    amenities = infrastructure_client.nearest_amenities(geojson_polygon)
    elevation_m = elevation_client.get_elevation(latitude, longitude)
    regional_baseline = float(os.getenv("REGIONAL_BASELINE_ELEVATION_M", str(elevation_m)))
    flood_proxy = elevation_client.estimate_flood_risk_proxy(
        latitude,
        longitude,
        regional_baseline_elevation_m=regional_baseline,
    )

    rera_df = _load_rera_or_empty()
    rera = match_parcel_to_rera(location["district"], rera_df)
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    snapshot_id = str(uuid4())
    evidence = [
        {
            "evidence_id": f"{snapshot_id}:satellite",
            "source_type": "satellite",
            "source_reference": getattr(satellite_client, "source_reference", "Satellite evidence provider"),
            "title": f"{getattr(satellite_client, 'source_reference', 'Satellite')} change series",
            "observed_at": now,
            "freshness": "derived",
            "summary": f"{len(change_series)} polygon-masked observations collected for the requested interval.",
        },
        {
            "evidence_id": f"{snapshot_id}:osm",
            "source_type": "openstreetmap",
            "source_reference": "Overpass API",
            "title": "Nearby infrastructure",
            "observed_at": now,
            "freshness": "live",
            "summary": "Nearest road and school distances measured from the polygon centroid.",
        },
        {
            "evidence_id": f"{snapshot_id}:elevation",
            "source_type": "open_elevation",
            "source_reference": "Open-Elevation API",
            "title": "Representative elevation",
            "observed_at": now,
            "freshness": "live",
            "summary": "Elevation sampled at the polygon centroid; not parcel-wide terrain sampling.",
        },
        {
            "evidence_id": f"{snapshot_id}:rera",
            "source_type": "maharera_seed",
            "source_reference": "MahaRERA static seed dataset",
            "title": "District-level RERA seed match",
            "observed_at": now,
            "freshness": "seed_data",
            "summary": "Exact case-insensitive district match only.",
        },
    ]
    sections = [location, metrics, rera, _satellite_facts(change_series), amenities, flood_proxy]
    completeness = round(100 * sum(section is not None for section in sections) / len(sections), 1)
    snapshot = {
        "parcel_id": str(uuid4()),
        "location": location,
        "geometry": geojson_polygon,
        "geometry_metadata": {
            **metrics,
            "boundary_source": "user_drawn",
            "boundary_verified": None,
        },
        "land_records": None,
        "rera": rera,
        "satellite": _satellite_facts(change_series),
        "infrastructure": amenities,
        "risk": {
            "flood_risk_score": flood_proxy["score"],
            "flood_risk_basis": flood_proxy["basis"],
            "elevation_m": elevation_m,
            "legal_risk_score": None,
            "accessibility_score": None,
        },
        "evidence": evidence,
        "metadata": {
            "last_updated": now,
            "data_completeness_pct": completeness,
            "analysis_date_from": start,
            "analysis_date_to": end,
            "analysis_snapshot_id": snapshot_id,
        },
    }
    _validate_snapshot(snapshot)
    return snapshot
