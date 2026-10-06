"""Evidence collection India-wide: coverage before collection, and no regional cache required."""

from __future__ import annotations

import pytest
from shapely.geometry import box

import etl_pipeline
from connectors import flood_indicators, river_flood
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


def test_provider_failure_is_unavailable_not_safe(offline, monkeypatch) -> None:
    def down(_polygon):
        raise river_flood.RiverFloodUnavailable("ID185_N20_E70: HTTP 503")

    monkeypatch.setattr(river_flood, "assess", down)
    snapshot = etl_pipeline.build_evidence_snapshot(KADAPA, "2025-01-01", "2026-01-01")
    river = next(c for c in snapshot["flood_indicators"]["components"] if c["mechanism"] == "river_flooding")
    assert river["status"] == "unavailable"
    assert "not evidence of safety" in river["summary"]
    assert "503" in snapshot["flood_indicators"]["unavailable"]["river_flood"]


def test_parcel_outside_india_runs_no_collector(monkeypatch) -> None:
    monkeypatch.setattr(etl_pipeline, "india_coverage", lambda: COVERAGE)

    def explode(*_args, **_kwargs):
        raise AssertionError("a collector ran for a parcel outside India")

    for target, name in ((etl_pipeline, "get_satellite_client"), (etl_pipeline, "region_for"),
                         (river_flood, "assess"), (flood_indicators, "surface_water")):
        monkeypatch.setattr(target, name, explode)
    with pytest.raises(etl_pipeline.OutsideCoverage) as caught:
        etl_pipeline.build_evidence_snapshot(PUNE, "2025-01-01", "2026-01-01")  # outside the test "India"
    assert caught.value.result["status"] == "outside_india"
