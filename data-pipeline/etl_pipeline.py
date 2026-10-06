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

from connectors import flood_indicators
from connectors.elevation_dem import ElevationClient, ElevationError
from connectors import river_flood
from connectors.local_osm import LocalOSM
from connectors.regions import LocalDataMissing, india_coverage, region_for, slug
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


class OutsideCoverage(Exception):
    """The drawn parcel is not inside India; no evidence is collected."""

    def __init__(self, result: dict[str, Any]) -> None:
        super().__init__(result.get("reason") or "outside coverage")
        self.result = result


def _overpass_fallback_enabled() -> bool:
    return os.getenv("OSM_OVERPASS_FALLBACK", "").strip().lower() in {"1", "true", "yes"}


# Water classes that count as a river/canal, and as a tank/lake ("eri"). An untagged
# natural=water polygon is most often a tank (eri, kere, cheruvu) in South India, so it is included there.
RIVER_CANAL = {"river", "canal"}
TANK_LAKE = {"lake", "reservoir", "pond", "basin", "tank", "water"}
POI_SEARCH_M = 5000.0


def _hit_fields(prefix: str, hit: dict[str, Any] | None, *, with_class: bool = False, with_point: bool = False) -> dict[str, Any]:
    fields: dict[str, Any] = {
        f"{prefix}_distance_m": hit["distance_m"] if hit else None,
        f"{prefix}_name": hit["name"] if hit else None,
    }
    if with_class:
        fields[f"{prefix}_type"] = hit["class"] if hit else None
    if with_point:
        fields[f"{prefix}_lat"] = hit["lat"] if hit else None
        fields[f"{prefix}_lon"] = hit["lon"] if hit else None
    return fields


def _local_amenities(osm: LocalOSM, geojson_polygon: dict[str, Any]) -> dict[str, Any]:
    """Nearest road, school, hospital, bus and rail station from the local extract."""
    lon, lat = InfrastructureClient._representative_point(geojson_polygon)
    road = osm.nearest(lon, lat, "road", max_distance_m=POI_SEARCH_M)
    school = osm.nearest(lon, lat, "school", max_distance_m=POI_SEARCH_M)
    road_tags = (road or {}).get("tags", {})
    access_tag = road_tags.get("access")
    return {
        "nearest_road_distance_m": road["distance_m"] if road else None,
        "nearest_road_type": road["class"] if road else None,
        "nearest_road_name": road["name"] if road else None,
        "nearest_road_access_tag": access_tag,
        "nearest_road_surface": road_tags.get("surface"),
        "nearest_road_lat": road["lat"] if road else None,
        "nearest_road_lon": road["lon"] if road else None,
        **_hit_fields("nearest_school", school, with_point=True),
        **_hit_fields("nearest_hospital", osm.nearest(lon, lat, "hospital", max_distance_m=POI_SEARCH_M)),
        **_hit_fields("nearest_bus", osm.nearest(lon, lat, "bus", max_distance_m=POI_SEARCH_M), with_class=True),
        **_hit_fields("nearest_rail_station", osm.nearest(lon, lat, "rail_station", max_distance_m=POI_SEARCH_M), with_class=True),
        "search_radius_m": POI_SEARCH_M,
        "distance_measurement": "straight_line_to_nearest_point_on_osm_geometry",
        "road_access_verified": False,
        "road_access_note": (
            "Proximity only. This is the straight-line distance from the parcel centroid to the nearest "
            "point on an OpenStreetMap way, not a routed travel distance, and it is not evidence of a legal "
            "right of way or of a physical connection to the parcel."
            + (f" The way is tagged access={access_tag}." if access_tag else "")
        ),
    }


def _water_distances(osm: LocalOSM, geojson_polygon: dict[str, Any]) -> dict[str, Any]:
    lon, lat = InfrastructureClient._representative_point(geojson_polygon)
    hits = [
        osm.nearest(lon, lat, "waterway", RIVER_CANAL, max_distance_m=POI_SEARCH_M),
        osm.nearest(lon, lat, "water", RIVER_CANAL, max_distance_m=POI_SEARCH_M),
    ]
    river = min((hit for hit in hits if hit), key=lambda hit: hit["distance_m"], default=None)
    tank = osm.nearest(lon, lat, "water", TANK_LAKE, max_distance_m=POI_SEARCH_M)
    return {
        **_hit_fields("nearest_river_canal", river, with_class=True),
        **_hit_fields("nearest_tank_lake", tank, with_class=True),
        "search_radius_m": POI_SEARCH_M,
    }


NRSC_REFERENCE = (
    "NRSC/ISRO Flood Affected Area Atlas of India (1998-2022): https://ndem.nrsc.gov.in/documents/downloads/"
    "allindia_flood_techdoc.pdf. Its spatial layers are hosted for viewing on the NDEM geoportal; no "
    "machine-readable download is offered, so it is not integrated."
)


def _river_summary(river: dict[str, Any] | None, error: str | None) -> str:
    if river is None:
        return f"River flood hazard not assessed: {error or 'no result'}. This is not evidence of safety."[:500]
    if river["status"] == "not_modelled":
        return "No river flood hazard tile covers this location; river flooding is not modelled here. This is not evidence of safety."
    by_rp = {item["return_period_years"]: item for item in river["scenarios"]}
    first = next((item for item in river["scenarios"] if item["flooded_area_m2"] > 0), None)
    if first is None:
        head = ("No modelled river inundation on the parcel in any scenario up to 1-in-500 years. The maps cover "
                "rivers with basins over ~500 km2 at ~90 m; they do not show small streams, rainfall waterlogging or coastal surge")
    else:
        rp100 = by_rp.get(100) or {}
        head = (
            f"Modelled river inundation first reaches the parcel in the 1-in-{first['return_period_years']}-year scenario "
            f"({first['flooded_share_of_parcel'] * 100:.0f}% of the parcel). 1-in-100-year: "
            f"{(rp100.get('flooded_share_of_parcel') or 0) * 100:.0f}% of the parcel"
            + (f", max depth {rp100['max_depth_m']} m" if rp100.get("max_depth_m") is not None else "")
        )
    near = (by_rp.get(100) or {}).get("surroundings_flooded_share")
    if near:
        head += f". Within {river.get('surroundings_m', 500):.0f} m, {near * 100:.0f}% of the land is modelled as flooded at 1-in-100 years"
    flags = []
    if river.get("permanent_water_area_m2"):
        flags.append(f"{river['permanent_water_area_m2']:,.0f} m2 is permanent water (excluded)")
    if river.get("quality_flagged_area_m2"):
        flags.append(f"{river['quality_flagged_area_m2']:,.0f} m2 is in a provider-flagged spurious-depth area (depths withheld)")
    if river["status"] == "partial":
        flags.append(f"only {river['assessed_share_of_parcel'] * 100:.0f}% of the parcel could be assessed")
    return (head + (". " + "; ".join(flags) if flags else "") + ". Modelled scenarios, not observed floods.")[:500]


def _flood_components(river, river_error, flood) -> list[dict[str, Any]]:
    """What each flood mechanism's evidence is, kept separate and never merged into a score."""
    sw, terrain, water = flood.get("surface_water"), flood.get("terrain"), flood.get("water_distances")
    errors = flood.get("errors") or {}
    river_status = "unavailable" if river is None else river["status"]
    if water:
        terrain_summary = _water_summary(water, terrain, errors.get("terrain"))
    else:
        terrain_summary = (
            (f"Parcel median elevation {terrain['parcel_elevation_m']} m. " if terrain else "")
            + f"Nearby water features unavailable: {errors.get('water_distances') or errors.get('terrain')}"
        )
    return [
        {"mechanism": "river_flooding", "status": river_status,
         "source": river_flood.DATASET,
         "period": "Modelled return-period scenarios (1-in-10 to 1-in-500 years), not observed events",
         "resolution": "~90 m", "coverage_share": river.get("assessed_share_of_parcel") if river else None,
         "summary": _river_summary(river, river_error)},
        {"mechanism": "historical_inundation", "status": "not_integrated",
         "source": "NRSC/ISRO Flood Affected Area Atlas of India",
         "period": "1998-2022", "resolution": None, "coverage_share": None, "summary": NRSC_REFERENCE},
        {"mechanism": "observed_surface_water", "status": "assessed" if sw else "unavailable",
         "source": "JRC Global Surface Water v1.4", "period": "1984-2021", "resolution": "~30 m",
         "coverage_share": None,
         "summary": (_surface_water_summary(sw) if sw else
                     f"Unavailable: {errors.get('surface_water') or errors.get('all')}")[:500]},
        {"mechanism": "terrain_and_nearby_water",
         "status": "assessed" if terrain and water else "partial" if terrain or water else "unavailable",
         "source": "Copernicus DEM GLO-30" + (" + OpenStreetMap" if water else ""),
         "period": "DEM from 2011-2015 acquisitions", "resolution": "~30 m", "coverage_share": None,
         "summary": terrain_summary[:500]},
        {"mechanism": "rainfall_waterlogging", "status": "not_assessed", "source": None, "period": None,
         "resolution": None, "coverage_share": None,
         "summary": "Not assessed: no rainfall, drainage-capacity or pluvial flood dataset is integrated. Urban "
                    "waterlogging can occur where no river flooding is modelled."},
        {"mechanism": "coastal_flooding", "status": "not_assessed", "source": None, "period": None,
         "resolution": None, "coverage_share": None,
         "summary": "Not assessed: no storm-surge or sea-level dataset is integrated. Distance from the sea or "
                    "elevation alone is not used as evidence of safety."},
    ]


def _metres(value: Any) -> str:
    return f"{value:,.0f} m" if isinstance(value, (int, float)) else "none mapped within 5 km"


def _local_infrastructure_summary(amenities: dict[str, Any]) -> str:
    road = amenities.get("nearest_road_distance_m")
    road_text = (
        f"road {_metres(road)} ({amenities.get('nearest_road_type') or 'class unrecorded'}"
        + (f", {amenities['nearest_road_name']}" if amenities.get("nearest_road_name") else "") + ")"
        if road is not None else "road: none mapped within 5 km"
    )
    bus = amenities.get("nearest_bus_distance_m")
    rail = amenities.get("nearest_rail_station_distance_m")
    return (
        f"Straight-line distances from the parcel centroid to the nearest point on each mapped feature: {road_text}; "
        f"school {_metres(amenities.get('nearest_school_distance_m'))}; "
        f"hospital {_metres(amenities.get('nearest_hospital_distance_m'))}; "
        f"bus {('stop/station ' + _metres(bus) + ' (' + str(amenities.get('nearest_bus_type')) + ')') if bus is not None else _metres(bus)}; "
        f"rail station {_metres(rail)}. Absence from OpenStreetMap is not proof that a facility does not exist."
    )[:500]


def _surface_water_summary(sw: dict[str, Any]) -> str:
    inside, around = sw["parcel"], sw["within_buffer"]

    def describe(part: dict[str, Any]) -> str:
        if not part.get("pixels"):
            return "no valid pixels"
        return (
            f"max occurrence {part['occurrence_max_pct']}%, mean {part['occurrence_mean_pct']}%, "
            f"water seen at least once on {part['water_ever_fraction'] * 100:.1f}% of {part['pixels']} pixels"
        )

    return (
        f"Inside the parcel: {describe(inside)}. Parcel plus {sw['buffer_m']:.0f} m: {describe(around)}. "
        "Occurrence is the share of valid Landsat observations (1984-2021) in which a 30 m pixel was open water. "
        "It records where water was seen - mostly tanks, rivers and seasonal water - and is NOT a flood-inundation "
        "history: short floods between revisits, floods under monsoon cloud and urban street flooding are largely missed."
    )[:500]


def _water_summary(water: dict[str, Any], terrain: dict[str, Any] | None, terrain_error: str | None) -> str:
    river = water.get("nearest_river_canal_distance_m")
    tank = water.get("nearest_tank_lake_distance_m")
    parts = [
        f"Nearest river/canal {_metres(river)}"
        + (f" ({water.get('nearest_river_canal_type')}{', ' + water['nearest_river_canal_name'] if water.get('nearest_river_canal_name') else ''})" if river is not None else ""),
        f"nearest tank/lake {_metres(tank)}"
        + (f" ({water['nearest_tank_lake_name']})" if tank is not None and water.get("nearest_tank_lake_name") else ""),
    ]
    if terrain and terrain.get("elevation_above_nearest_water_m") is not None:
        parts.append(
            f"parcel median elevation {terrain['parcel_elevation_m']:.1f} m is {terrain['elevation_above_nearest_water_m']:+.1f} m "
            f"relative to the nearest mapped water feature ({terrain['nearest_water_feature_class']}, "
            f"{terrain['nearest_water_feature_distance_m']:,.0f} m away). Terrain indicator only: not HAND (no drainage "
            "routing), not a flood probability, and the DEM is a surface model that includes buildings and trees"
        )
    elif terrain:
        parts.append(f"no mapped water feature within {terrain['search_radius_m']:.0f} m, so no height above water is reported")
    elif terrain_error:
        parts.append(f"height above water unavailable: {terrain_error}")
    return ("; ".join(parts) + ".")[:500]


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
    """Physical measurements only; the 0-100 terrain-position figure is not shown as a headline."""
    if not isinstance(elevation_m, (int, float)):
        return f"Elevation unavailable: {flood_proxy.get('basis') or 'no value returned.'}"[:500]
    baseline, relief = flood_proxy.get("baseline_m"), flood_proxy.get("relief_m")
    parts = [f"Centroid elevation {elevation_m:,.1f} m (Copernicus GLO-30 surface model)"]
    if isinstance(baseline, (int, float)):
        difference = elevation_m - baseline
        parts.append(
            f"{abs(difference):.1f} m {'above' if difference >= 0 else 'below'} the median of the surrounding "
            f"terrain within 5 km ({baseline:,.1f} m)"
        )
    if isinstance(relief, (int, float)):
        parts.append(f"local relief {relief:,.0f} m")
    return ("; ".join(parts) + ". Terrain position only: it does not measure rainfall, drainage, river or coastal flooding.")[:500]


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


def _satellite_summary(series: list[dict[str, Any]], client: Any, metrics: dict[str, Any]) -> str:
    """Describe what was actually retrieved, including the resolution caveat."""
    if not series:
        return "No usable satellite observations were retrieved."
    diagnostics = getattr(client, "last_diagnostics", {}) or {}
    pixels = [row.get("usable_pixel_count") or 0 for row in series]
    resolution = series[0].get("resolution_m") or 10.0
    area = metrics.get("area_m2") or 0.0
    parts = [
        f"{len(series)} cloud-screened observations from "
        f"{getattr(client, 'source_reference', 'satellite imagery')} "
        f"({series[0]['date']} to {series[-1]['date']})",
        f"{resolution:.0f} m pixels, {min(pixels)}-{max(pixels)} usable inside the parcel",
    ]
    if diagnostics.get("scenes_matched"):
        parts.append(
            f"{diagnostics['scenes_matched']} scenes matched, "
            f"{diagnostics.get('observations_rejected', 0)} rejected for cloud or too few pixels"
        )
    # A small plot is mostly edge pixels, which borrow reflectance from next door.
    if area and area < (resolution ** 2) * 20:
        parts.append(
            f"the parcel is {area:,.0f} m2, only about {area / (resolution ** 2):.0f} native pixels, "
            "so values include neighbouring land and single-date readings are unreliable"
        )
    parts.append("This is a land-cover signal, not evidence of investment or development approval")
    return ". ".join(parts) + "."


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

    # Coverage first: outside India nothing is collected at all. A missing
    # boundary raises LocalDataMissing rather than letting the parcel through.
    coverage_check = india_coverage().check(geojson_polygon)
    if coverage_check["status"] != "inside":
        raise OutsideCoverage(coverage_check)

    # Regional data only adds evidence; its absence never blocks the India-wide collectors.
    region = region_for(geojson_polygon)
    coverage_check["regional_data"] = region.slug if region else None
    local_osm: LocalOSM | None = None
    local_osm_error: str | None = None
    if region is not None:
        try:
            local_osm = LocalOSM(region.osm_store)
        except LocalDataMissing as error:
            local_osm_error = str(error)
    else:
        main_state = (coverage_check["states"] or [{}])[0].get("name") or "this area"
        local_osm_error = (
            f"No regional OpenStreetMap data is installed for {main_state}. "
            f"Install it with: terrascope.cmd fetch-data {slug(main_state)}"
        )
    osm_meta = (local_osm.meta if local_osm else {}) or {}

    infrastructure_client = InfrastructureClient()
    satellite_client = get_satellite_client()
    # Copernicus GLO-30 (cached tiles, else read remotely) replaces the Open-Elevation web call.
    elevation_client = flood_indicators.LocalDemElevationClient()
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
        if local_osm is not None:
            return _local_amenities(local_osm, geojson_polygon), None
        if not _overpass_fallback_enabled():
            return dict(_EMPTY_AMENITIES), f"{local_osm_error} The Overpass fallback is off (OSM_OVERPASS_FALLBACK)."
        try:
            return infrastructure_client.nearest_amenities(geojson_polygon), None
        except (InfrastructureError, ValueError) as error:
            # One overloaded public endpoint must not cost the user the whole
            # parcel report. Report the gap instead of inventing distances.
            LOGGER.warning("Infrastructure evidence unavailable: %s", error)
            return dict(_EMPTY_AMENITIES), str(error)

    def collect_flood() -> dict[str, Any]:
        """Flood-relevant evidence. Each part fails on its own and says why."""
        out: dict[str, Any] = {"surface_water": None, "terrain": None, "water_distances": None, "errors": {}}
        try:
            out["surface_water"] = flood_indicators.surface_water(geojson_polygon)
        except Exception as error:  # noqa: BLE001 - reported, never invented
            out["errors"]["surface_water"] = str(error)
        try:
            out["terrain"] = flood_indicators.terrain_above_water(geojson_polygon, local_osm)
        except Exception as error:  # noqa: BLE001
            out["errors"]["terrain"] = str(error)
        if local_osm is not None:
            out["water_distances"] = _water_distances(local_osm, geojson_polygon)
        else:
            out["errors"]["water_distances"] = local_osm_error
        return out

    def collect_river_flood() -> tuple[dict[str, Any] | None, str | None]:
        try:
            return river_flood.assess(geojson_polygon), None
        except Exception as error:  # noqa: BLE001 - a provider failure is "not assessed", never "no flooding"
            LOGGER.warning("River flood hazard unavailable: %s", error)
            return None, str(error)[:300]

    # These four call different providers and do not depend on each other, so
    # run them together: the analysis takes as long as the slowest, not the sum.
    # Public Overpass queues requests for ~20s+ regardless of query size, so the
    # optional layers also get a deadline; past it the report ships without them
    # rather than making the user wait, and says which layer is missing.
    deadline = float(os.getenv("EVIDENCE_COLLECTION_DEADLINE_SECONDS", "35"))
    pool = ThreadPoolExecutor(max_workers=6)
    try:
        location_future = pool.submit(collect_location)
        satellite_future = pool.submit(satellite_client.get_change_series, geojson_polygon, start, end)
        amenities_future = pool.submit(collect_amenities)
        terrain_future = pool.submit(collect_terrain)
        flood_future = pool.submit(collect_flood)
        river_future = pool.submit(collect_river_flood)

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
        flood = finish(
            flood_future,
            {"surface_water": None, "terrain": None, "water_distances": None,
             "errors": {"all": f"Flood indicators exceeded the {deadline:.0f}s evidence deadline."}},
            "Flood indicators",
        )
        river, river_error = finish(
            river_future, (None, f"River flood hazard maps exceeded the {deadline:.0f}s evidence deadline."), "River flood hazard"
        )
    finally:
        # Do not block the response on a request that already missed its deadline.
        pool.shutdown(wait=False)
    location = _location_from_context(latitude, longitude, location_context, address)
    satellite_is_demo = bool(getattr(satellite_client, "is_demo", False))

    if local_osm is not None:
        local_osm.close()
    components = _flood_components(river, river_error, flood)
    usable = [c for c in components if c["status"] in ("assessed", "partial")]

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
                else "Land-cover change (NDVI/NDBI) from observed imagery"
            ),
            "observed_at": now,
            # Invented data is seed_data, never "derived" from a real observation.
            "freshness": "seed_data" if satellite_is_demo else "live",
            "summary": (
                f"{len(change_series)} INVENTED observations generated for demo mode because no "
                "imagery provider returned data. This is not imagery and must not be read as "
                "evidence of real vegetation or construction change."
                if satellite_is_demo
                else _satellite_summary(change_series, satellite_client, metrics)
            ),
        },
        {
            "evidence_id": f"{snapshot_id}:osm",
            "source_type": "openstreetmap",
            "source_reference": (
                f"OpenStreetMap, Geofabrik extract ({osm_meta.get('extract_file', 'local')}), region {region.slug}"
                if local_osm and region else "Overpass API (opt-in fallback)" if _overpass_fallback_enabled()
                else "OpenStreetMap (regional data not installed)"
            ),
            "title": "Nearby infrastructure",
            # The evidence date is the extract's data date, not the moment of the query.
            "observed_at": osm_meta.get("data_as_of") or now,
            "freshness": "cached" if local_osm else "live",
            "licence": "ODbL 1.0 - (c) OpenStreetMap contributors",
            "resolution": "vector features",
            "summary": (
                f"OpenStreetMap infrastructure is unavailable for this parcel: {amenities_error} "
                "No road or school distance is reported rather than an estimated one."
                if amenities_error
                else _local_infrastructure_summary(amenities) if local_osm else _infrastructure_summary(amenities)
            )[:500],
        },
        {
            "evidence_id": f"{snapshot_id}:elevation",
            "source_type": "copernicus_dem",
            "source_reference": "Copernicus DEM GLO-30 (via Microsoft Planetary Computer; "
                                + flood_indicators.dem_access(latitude, longitude) + ")",
            "title": "Elevation and terrain position (not flood risk)",
            "observed_at": f"{flood_indicators.DEM_PRODUCT_DATE}T00:00:00Z",
            "freshness": "cached",
            "licence": flood_indicators.DEM_LICENCE,
            "resolution": "~30 m surface model (includes buildings and trees)",
            "observation_period": flood_indicators.DEM_PERIOD,
            "summary": _elevation_summary(elevation_m, flood_proxy),
        },
        {
            "evidence_id": f"{snapshot_id}:river-flood",
            "source_type": "jrc_flood_hazard",
            "source_reference": f"{river_flood.DATASET} (doi:10.2905/JRC.VD32YWG)",
            "title": "Modelled river flooding by return period (not observed events)",
            # The maps are the 2026-01-12 release of modelled scenarios, not an observation date.
            "observed_at": "2026-01-12T00:00:00Z",
            "freshness": "live" if river and river.get("cache") == "new" else "cached",
            "licence": river_flood.LICENCE,
            "resolution": "~90 m",
            "observation_period": "Modelled scenarios, 1-in-10 to 1-in-500 years",
            "summary": _river_summary(river, river_error),
        },
        {
            "evidence_id": f"{snapshot_id}:surface-water",
            "source_type": "jrc_gsw",
            "source_reference": "JRC Global Surface Water v1.4 (EC JRC/Google)"
                                + (f", {flood['surface_water']['data_access']}" if flood.get("surface_water") else ""),
            "title": "Surface water observed 1984-2021 (not flood history)",
            "observed_at": "2021-12-31T00:00:00Z",
            "freshness": "cached",
            "licence": flood_indicators.GSW_LICENCE,
            "resolution": "30 m",
            "observation_period": "1984-03 to 2021-12",
            "summary": (
                _surface_water_summary(flood["surface_water"]) if flood.get("surface_water")
                else f"Surface-water evidence unavailable: {flood['errors'].get('surface_water') or flood['errors'].get('all')}"
            )[:500],
        },
        {
            "evidence_id": f"{snapshot_id}:water-features",
            "source_type": "osm_water",
            "source_reference": (
                f"OpenStreetMap water features ({osm_meta.get('extract_file', 'regional data not installed')})"
                + (" + Copernicus DEM GLO-30" if flood.get("terrain") else "")
            ),
            "title": "Distance and height relative to mapped rivers, canals and tanks",
            "observed_at": osm_meta.get("data_as_of") or now,
            "freshness": "cached",
            "licence": "ODbL 1.0 - (c) OpenStreetMap contributors" + ("; Copernicus DEM licence" if flood.get("terrain") else ""),
            "resolution": "vector features; DEM 30 m",
            "summary": (
                _water_summary(flood["water_distances"], flood.get("terrain"), flood["errors"].get("terrain"))
                if flood.get("water_distances")
                else f"Water-feature evidence unavailable: {flood['errors'].get('water_distances') or flood['errors'].get('all')}"
            )[:500],
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
        "surface_water": flood.get("surface_water"),
        "water_features": flood.get("water_distances"),
        "river_flood_hazard": river,
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
        # Evidence only. Flood Safety stays unscored until a rule is approved.
        "flood_indicators": {
            "scoring_status": "not_scored",
            # Evidence exists for some mechanisms but no validated method combines them into a score.
            "assessment_status": "partial" if usable else "unavailable",
            "components": components,
            "river_flood": river,
            "surface_water": flood.get("surface_water"),
            "terrain": flood.get("terrain"),
            "water_distances": flood.get("water_distances"),
            "unavailable": {
                key: value for key, value in {**(flood.get("errors") or {}), "river_flood": river_error}.items() if value
            } or None,
        },
        "coverage": coverage_check,
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
