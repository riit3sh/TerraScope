"""Blocking evidence collection for one TerraScope parcel analysis."""

from __future__ import annotations

import json
import logging
import os
import time
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FuturesTimeout
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

import pandas as pd
from jsonschema import Draft202012Validator, FormatChecker

from connectors.elevation_dem import ElevationClient, ElevationError
from connectors.osm_infrastructure import InfrastructureClient, InfrastructureError
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
LOGGER = logging.getLogger(__name__)
_EMPTY_AMENITIES: dict[str, Any] = {
    "nearest_road_distance_m": None, "nearest_road_type": None, "nearest_school_distance_m": None,
    "nearest_road_lat": None, "nearest_road_lon": None,
    "nearest_school_lat": None, "nearest_school_lon": None,
}


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


def _load_rera_or_empty() -> tuple[pd.DataFrame, Path, bool]:
    """Load the RERA seed CSV, reporting whether one was actually configured."""
    seed_path = Path(os.getenv("RERA_SEED_PATH", str(Path(__file__).parent / "data" / "raw" / "maharera_seed.csv")))
    if not seed_path.exists():
        return pd.DataFrame({"district": pd.Series(dtype="string")}), seed_path, False
    return load_rera_seed_dataset(seed_path), seed_path, True


def _infrastructure_summary(amenities: dict[str, Any]) -> str:
    road = amenities.get("nearest_road_distance_m")
    road_type = amenities.get("nearest_road_type")
    school = amenities.get("nearest_school_distance_m")
    parts = [
        f"nearest road {road:,.0f} m ({road_type or 'type unrecorded'})" if isinstance(road, (int, float)) else "no road found within the search radius",
        f"nearest school {school:,.0f} m" if isinstance(school, (int, float)) else "no school found within the search radius",
    ]
    return f"Measured from the polygon centroid: {'; '.join(parts)}."


def _elevation_summary(elevation_m: float | None, flood_proxy: dict[str, Any]) -> str:
    head = f"Centroid elevation {elevation_m:,.1f} m." if isinstance(elevation_m, (int, float)) else "Centroid elevation unavailable."
    return f"{head} {flood_proxy.get('basis') or 'No flood-risk basis recorded.'}"[:500]


def _rera_summary(match: dict[str, Any], district: str | None, seed_path: Path, seed_loaded: bool) -> str:
    """Describe the district-level RERA seed lookup without overclaiming."""
    if not seed_loaded:
        return (
            f"No RERA seed dataset is configured at {seed_path.name}; "
            "this parcel's RERA status is unknown."
        )
    count = match.get("district_match_count") or 0
    if not count:
        return (
            f"No registered project in the seed shares district {district or 'unknown'}. "
            "The seed is one state's partial export, so this parcel's RERA status stays unknown."
        )
    candidate = match.get("district_candidate") or {}
    registration = candidate.get("rera_registration_number") or "registration number unrecorded"
    promoter = candidate.get("promoter_name") or "promoter unrecorded"
    return (
        f"{count} registered project(s) share district {district}; nearest candidate is "
        f"{registration} ({promoter}). District-level candidate only - this is not evidence "
        "that this parcel is registered, so its RERA status stays unknown."
    )[:500]


def _data_coverage(checks: dict[str, Any]) -> float:
    """Percentage of evidence fields actually obtained, counted field by field."""
    return round(100.0 * sum(value is not None for value in checks.values()) / len(checks), 1)


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

    def collect_location() -> dict[str, Any] | None:
        try:
            if address:
                geocoded = infrastructure_client.geocode_address(address)
                return geocoded[0] if geocoded else None
            return infrastructure_client.reverse_geocode(latitude, longitude)
        except (InfrastructureError, ValueError) as error:
            LOGGER.warning("Geocoding unavailable; falling back to coordinates only: %s", error)
            return None

    def collect_terrain() -> tuple[float | None, dict[str, Any]]:
        try:
            configured = os.getenv("REGIONAL_BASELINE_ELEVATION_M")
            # Only an explicitly configured datum overrides the sampled terrain.
            # Defaulting this to the parcel's own elevation made every delta zero,
            # so every parcel scored exactly 50.
            proxy = elevation_client.estimate_terrain_relative_elevation(
                latitude,
                longitude,
                float(configured) if configured not in (None, "") else None,
            )
            return proxy["elevation_m"], proxy
        except (ElevationError, ValueError) as error:
            # Elevation is optional evidence; do not block the report or invent a score.
            return None, {
                "score": None,
                "basis": f"Representative elevation unavailable at the polygon centroid: {error}",
            }

    def collect_amenities() -> tuple[dict[str, Any], str | None]:
        """Infrastructure is optional evidence; a gap is reported, never invented."""
        try:
            return infrastructure_client.nearest_amenities(geojson_polygon), None
        except (InfrastructureError, ValueError) as error:
            # One overloaded public endpoint must not cost the user the whole
            # parcel report. Report the gap instead of inventing distances.
            LOGGER.warning("Infrastructure evidence unavailable: %s", error)
            return dict(_EMPTY_AMENITIES), str(error)

    # These four call different providers and do not depend on each other, so
    # run them together: the analysis takes as long as the slowest, not the sum.
    # Public Overpass queues requests for ~20s+ regardless of query size, so the
    # optional layers also get a deadline; past it the report ships without them
    # rather than making the user wait, and says which layer is missing.
    deadline = float(os.getenv("EVIDENCE_COLLECTION_DEADLINE_SECONDS", "35"))
    pool = ThreadPoolExecutor(max_workers=4)
    try:
        location_future = pool.submit(collect_location)
        satellite_future = pool.submit(satellite_client.get_change_series, geojson_polygon, start, end)
        amenities_future = pool.submit(collect_amenities)
        terrain_future = pool.submit(collect_terrain)

        started = time.monotonic()

        def finish(future, fallback, label):
            remaining = max(1.0, deadline - (time.monotonic() - started))
            try:
                return future.result(timeout=remaining)
            except FuturesTimeout:
                LOGGER.warning("%s did not return within the %.0fs deadline.", label, deadline)
                future.cancel()
                return fallback

        location_context = finish(location_future, None, "Geocoding")
        change_series = finish(satellite_future, [], "Satellite collection")
        amenities, amenities_error = finish(
            amenities_future,
            (_EMPTY_AMENITIES, f"the lookup exceeded the {deadline:.0f}s evidence deadline."),
            "Infrastructure lookup",
        )
        elevation_m, flood_proxy = finish(
            terrain_future,
            (None, {"score": None, "basis": f"Terrain sampling exceeded the {deadline:.0f}s evidence deadline."}),
            "Terrain sampling",
        )
    finally:
        # Do not block the response on a request that already missed its deadline.
        pool.shutdown(wait=False)
    location = _location_from_context(latitude, longitude, location_context, address)
    satellite_is_demo = bool(getattr(satellite_client, "is_demo", False))

    rera_df, rera_seed_path, rera_seed_loaded = _load_rera_or_empty()
    rera_match = match_parcel_to_rera(location["district"], rera_df)
    rera = rera_match["rera"]
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    snapshot_id = str(uuid4())
    evidence = [
        {
            "evidence_id": f"{snapshot_id}:satellite",
            "source_type": "satellite",
            "source_reference": getattr(satellite_client, "source_reference", "Satellite evidence provider"),
            "title": (
                "SYNTHETIC demo satellite series"
                if satellite_is_demo
                else f"{getattr(satellite_client, 'source_reference', 'Satellite')} change series"
            ),
            "observed_at": now,
            # Invented data is seed_data, never "derived" from a real observation.
            "freshness": "seed_data" if satellite_is_demo else "derived",
            "summary": (
                f"{len(change_series)} INVENTED observations generated for demo mode because no "
                "AppEEARS credentials are configured. This is not imagery and must not be read as "
                "evidence of real vegetation or construction change."
                if satellite_is_demo
                else f"{len(change_series)} polygon-masked observations collected for the requested interval."
            ),
        },
        {
            "evidence_id": f"{snapshot_id}:osm",
            "source_type": "openstreetmap",
            "source_reference": "Overpass API",
            "title": "Nearby infrastructure",
            "observed_at": now,
            "freshness": "live",
            "summary": (
                f"OpenStreetMap infrastructure is unavailable for this parcel: {amenities_error} "
                "No road or school distance is reported rather than an estimated one."
                if amenities_error
                else _infrastructure_summary(amenities)
            ),
        },
        {
            "evidence_id": f"{snapshot_id}:elevation",
            "source_type": "open_elevation",
            "source_reference": "Open-Elevation API",
            "title": "Representative elevation (terrain indicator, not flood risk)",
            "observed_at": now,
            "freshness": "live",
            "summary": _elevation_summary(elevation_m, flood_proxy),
        },
        {
            "evidence_id": f"{snapshot_id}:rera",
            "source_type": "maharera_seed",
            "source_reference": "MahaRERA static seed dataset",
            "title": "District-level RERA seed lookup",
            "observed_at": now,
            "freshness": "seed_data" if rera_seed_loaded else "derived",
            "summary": _rera_summary(rera_match, location["district"], rera_seed_path, rera_seed_loaded),
        },
    ]
    satellite_facts = _satellite_facts(change_series)
    # Count the fields we actually obtained; these sections are always dicts, so
    # testing the sections themselves would report 100% even with nothing in them.
    completeness = _data_coverage({
        "district": location.get("district"),
        "area_m2": metrics.get("area_m2"),
        "satellite_series": None if satellite_facts["change_type"] == "insufficient_evidence" else True,
        "nearest_road": amenities.get("nearest_road_distance_m"),
        "nearest_school": amenities.get("nearest_school_distance_m"),
        "elevation": elevation_m,
        "flood_proxy": flood_proxy.get("score"),
        "rera_status": rera.get("is_rera_project"),
        "land_records": None,  # no land-records connector exists yet
    })
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
        "satellite": satellite_facts,
        "infrastructure": amenities,
        "risk": {
            # No flood hazard dataset is integrated, so flood risk stays unknown.
            # The elevation comparison below is a terrain indicator, not flooding:
            # it says nothing about rainfall, drainage, rivers or the coast, and
            # writing it into flood_risk_score presented it as a flood probability.
            "flood_risk_score": None,
            "flood_risk_basis": None,
            "flood_assessment_status": "unavailable",
            "terrain_relative_elevation_score": flood_proxy["score"],
            "terrain_basis": flood_proxy["basis"],
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
