"""Evidence collection India-wide: coverage before collection, and no regional cache required."""

from __future__ import annotations

import pytest
from shapely.geometry import box

import etl_pipeline
from connectors import flood_indicators, land_cover_history, river_flood
from connectors.regions import IndiaCoverage

STATE = {"name": "Andhra Pradesh", "iso": "IN-AP", "geometry": box(77.0, 13.0, 80.0, 16.0)}
COVERAGE = IndiaCoverage([STATE], STATE["geometry"], {"source": "test boundary", "licence": "test"})
KADAPA = {"type": "Polygon", "coordinates": [[[78.82, 14.47], [78.821, 14.47], [78.821, 14.471], [78.82, 14.471], [78.82, 14.47]]]}
PUNE = {"type": "Polygon", "coordinates": [[[73.85, 18.52], [73.851, 18.52], [73.851, 18.521], [73.85, 18.521], [73.85, 18.52]]]}


class _NoImagery:
    source_reference = "test imagery"
    is_demo = False
    last_diagnostics: dict = {}

    def get_change_series(self, *_args):
        return []


def _river_result() -> dict:
    scenarios = [{"return_period_years": rp, "annual_exceedance_probability": round(1 / rp, 4),
                  "flooded_area_m2": 0.0 if rp < 100 else 5000.0, "flooded_share_of_parcel": 0.0 if rp < 100 else 0.42,
                  "flagged_flooded_area_m2": 0.0, "max_depth_m": None if rp < 100 else 0.8, "mean_depth_m": None if rp < 100 else 0.5,
                  "zero_depth_area_m2": 0.0, "no_modelled_inundation_area_m2": 0.0} for rp in river_flood.RETURN_PERIODS]
    return {"status": "assessed", "dataset": river_flood.DATASET, "licence": river_flood.LICENCE, "resolution": "~90 m",
            "assessed_share_of_parcel": 1.0, "permanent_water_area_m2": 0.0, "quality_flagged_area_m2": 0.0,
            "parcel_area_m2": 11900.0, "scenarios": scenarios, "tiles": ["ID185_N20_E70"], "cache": "new"}


@pytest.fixture()
def offline(monkeypatch):
    """Every provider replaced: no network, no regional cache."""
    monkeypatch.setattr(etl_pipeline, "india_coverage", lambda: COVERAGE)
    monkeypatch.setattr(etl_pipeline, "region_for", lambda _polygon: None)
    monkeypatch.setattr(etl_pipeline, "get_satellite_client", lambda: _NoImagery())
    monkeypatch.setattr(etl_pipeline.InfrastructureClient, "geocode_address", lambda *_a: [])
    monkeypatch.setattr(etl_pipeline.InfrastructureClient, "reverse_geocode", lambda *_a: None)
    monkeypatch.setattr(flood_indicators.LocalDemElevationClient, "get_elevations", lambda self, points: [210.0] + [200.0] * (len(points) - 1))
    monkeypatch.setattr(flood_indicators, "dem_access", lambda *_a: "test tiles")
    monkeypatch.setattr(flood_indicators, "surface_water", lambda _p: {
        "parcel": {"pixels": 12, "occurrence_max_pct": 0, "occurrence_mean_pct": 0.0, "water_ever_fraction": 0.0},
        "within_buffer": {"pixels": 900, "occurrence_max_pct": 40, "occurrence_mean_pct": 1.0, "water_ever_fraction": 0.05},
        "buffer_m": 500.0, "observation_period": "1984-03 to 2021-12", "resolution_m": 30,
        "dataset": "JRC Global Surface Water v1.4", "data_access": "read remotely from JRC"})

    def terrain(_polygon, osm):
        assert osm is None, "no regional store is installed, so no OSM water features may be used"
        return {"parcel_elevation_m": 210.0, "water_features_available": False}

    monkeypatch.setattr(flood_indicators, "terrain_above_water", terrain)
    monkeypatch.setattr(river_flood, "assess", lambda _p: _river_result())
    trend = {"first_year": 2017, "first_share": 0.2, "last_year": 2023, "last_share": 0.3, "years_used": 7,
             "slope_pts_per_year": 1.6}
    monkeypatch.setattr(land_cover_history, "assess", lambda _p: {
        "status": "assessed", "parcel": [{"year": 2017, "dominant": "crops"}], "surroundings": [],
        "trend_within_1km": trend, "trend_1_to_3km": None, "cache": "new"})


def test_indian_parcel_without_regional_data_still_collects_india_wide_evidence(offline) -> None:
    snapshot = etl_pipeline.build_evidence_snapshot(KADAPA, "2025-01-01", "2026-01-01")  # schema-validated inside

    assert snapshot["coverage"]["status"] == "inside"
    assert snapshot["coverage"]["states"][0]["name"] == "Andhra Pradesh"
    assert snapshot["coverage"]["regional_data"] is None
    # Accessibility needs the regional store: unavailable, with the install command, never estimated.
    assert snapshot["infrastructure"]["nearest_road_distance_m"] is None
    osm_row = next(e for e in snapshot["evidence"] if e["source_type"] == "openstreetmap")
    assert "terrascope.cmd fetch-data andhra-pradesh" in osm_row["summary"]
    # India-wide collectors ran regardless.
    flood = snapshot["flood_indicators"]
    assert flood["assessment_status"] == "partial"
    river = next(c for c in flood["components"] if c["mechanism"] == "river_flooding")
    assert river["status"] == "assessed" and "1-in-100-year" in river["summary"]
    assert flood["surface_water"]["data_access"] == "read remotely from JRC"
    assert flood["water_distances"] is None and "fetch-data" in flood["unavailable"]["water_distances"]
    assert snapshot["risk"]["flood_risk_score"] is None  # evidence only, never a score
    elevation_row = next(e for e in snapshot["evidence"] if e["source_type"] == "copernicus_dem")
    assert "/100" not in elevation_row["summary"]
    # The area's development history is India-wide too.
    assert snapshot["land_cover_history"]["trend_within_1km"]["slope_pts_per_year"] == 1.6
    land_row = next(e for e in snapshot["evidence"] if e["source_type"] == "land_cover")
    assert "Within 1 km: built area 20% (2017) to 30% (2023)" in land_row["summary"]


def test_provider_failure_is_unavailable_not_safe(offline, monkeypatch) -> None:
    def down(_polygon):
        raise river_flood.RiverFloodUnavailable("ID185_N20_E70: HTTP 503")

    monkeypatch.setattr(river_flood, "assess", down)
    snapshot = etl_pipeline.build_evidence_snapshot(KADAPA, "2025-01-01", "2026-01-01")
    river = next(c for c in snapshot["flood_indicators"]["components"] if c["mechanism"] == "river_flooding")
    assert river["status"] == "unavailable"
    assert "not evidence of safety" in river["summary"]
    assert "503" in snapshot["flood_indicators"]["unavailable"]["river_flood"]


def test_land_cover_failure_is_unavailable_not_no_development(offline, monkeypatch) -> None:
    def down(_polygon):
        raise RuntimeError("HTTP 429")

    monkeypatch.setattr(land_cover_history, "assess", down)
    snapshot = etl_pipeline.build_evidence_snapshot(KADAPA, "2025-01-01", "2026-01-01")
    assert snapshot["land_cover_history"] == {"status": "unavailable", "error": "HTTP 429"}
    assert "unavailable: HTTP 429" in next(e for e in snapshot["evidence"] if e["source_type"] == "land_cover")["summary"]


def test_parcel_outside_india_runs_no_collector(monkeypatch) -> None:
    monkeypatch.setattr(etl_pipeline, "india_coverage", lambda: COVERAGE)

    def explode(*_args, **_kwargs):
        raise AssertionError("a collector ran for a parcel outside India")

    for target, name in ((etl_pipeline, "get_satellite_client"), (etl_pipeline, "region_for"),
                         (river_flood, "assess"), (flood_indicators, "surface_water"), (land_cover_history, "assess")):
        monkeypatch.setattr(target, name, explode)
    with pytest.raises(etl_pipeline.OutsideCoverage) as caught:
        etl_pipeline.build_evidence_snapshot(PUNE, "2025-01-01", "2026-01-01")  # outside the test "India"
    assert caught.value.result["status"] == "outside_india"


def _ring(*points):
    return {"type": "Polygon", "coordinates": [[list(p) for p in points]]}


@pytest.mark.parametrize("polygon, message", [
    # 2026-10-11: these were analysed (bowtie, 2-degree box) or called "outside India".
    (_ring((79.13, 12.97), (79.14, 12.98), (79.14, 12.97), (79.13, 12.98), (79.13, 12.97)), "edges do not cross"),
    (_ring((0, 0), (2, 2), (2, 0), (0, 1), (0, 0)), "edges do not cross"),
    (_ring((79.13, 12.97), (79.14, 12.97), (79.15, 12.97), (79.13, 12.97)), "encloses no area"),
    (_ring((279.13, 12.97), (279.14, 12.97), (279.14, 12.98), (279.13, 12.97)), "out of range"),
    (_ring((78, 12), (80, 12), (80, 14), (78, 14), (78, 12)), "up to 1,000 ha"),
])
def test_invalid_boundaries_are_refused_before_collection(offline, polygon, message):
    with pytest.raises(ValueError, match=message):
        etl_pipeline.build_evidence_snapshot(polygon, "2025-01-01", "2026-01-01")
