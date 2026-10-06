"""Coverage check and local OpenStreetMap queries, on small synthetic stores."""

from __future__ import annotations

import pytest
from shapely.geometry import LineString, Point, Polygon, box

from connectors.local_osm import Coverage, LocalDataMissing, LocalOSM, create_store, write_features


def _parcel(lon: float, lat: float, size: float = 0.001) -> dict:
    return {"type": "Polygon", "coordinates": [[
        [lon, lat], [lon + size, lat], [lon + size, lat + size], [lon, lat + size], [lon, lat],
    ]]}


# A square "state" with a square enclave cut out of it, like Puducherry inside Tamil Nadu.
STATE = box(78.0, 10.0, 80.0, 12.0).difference(box(79.0, 11.0, 79.2, 11.2))
COVERAGE = Coverage(STATE, {"source": "test", "licence": "test", "data_as_of": "2026-01-01"})


def test_parcel_inside_coverage() -> None:
    assert COVERAGE.check(_parcel(78.5, 10.5))["status"] == "inside"


def test_parcel_in_enclave_is_outside() -> None:
    result = COVERAGE.check(_parcel(79.1, 11.1))
    assert result["status"] == "outside"
    assert "Tamil Nadu" in result["reason"]


def test_parcel_crossing_the_border_is_outside() -> None:
    result = COVERAGE.check(_parcel(79.9995, 10.5))
    assert result["status"] == "outside"
    assert "crosses the edge" in result["reason"]


def test_parcel_far_away_is_outside() -> None:
    result = COVERAGE.check(_parcel(73.85, 18.52))  # Pune
    assert result["status"] == "outside"
    assert "outside Tamil Nadu" in result["reason"]


ORIGIN = (79.13, 12.92)  # (lon, lat), Vellore


@pytest.fixture()
def store(tmp_path):
    lon, lat = ORIGIN
    path = tmp_path / "osm.sqlite"
    connection = create_store(path)
    write_features(connection, [
        # A 2 km road passing ~22 m north of the origin; its midpoint is ~1 km away.
        ("road", "primary", "Long Road", "w1", {"surface": "asphalt"}, LineString([(lon, lat + 0.0002), (lon + 0.02, lat + 0.0002)])),
        ("road", "residential", "Far Road", "w2", {}, LineString([(lon, lat + 0.01), (lon + 0.01, lat + 0.01)])),
        # The origin sits inside this school's grounds.
        ("school", "school", "Inside School", "w3", {}, Polygon([(lon - 0.001, lat - 0.001), (lon + 0.001, lat - 0.001), (lon + 0.001, lat + 0.001), (lon - 0.001, lat + 0.001)])),
        ("waterway", "drain", "Drain", "w4", {}, LineString([(lon - 0.01, lat - 0.002), (lon + 0.01, lat - 0.002)])),
        ("waterway", "river", "Palar", "w5", {}, LineString([(lon - 0.05, lat - 0.025), (lon + 0.05, lat - 0.025)])),
        ("hospital", "hospital", "Hospital", "n6", {}, Point(lon + 0.04, lat)),
    ])
    connection.executemany("INSERT INTO store_meta VALUES (?, ?)", [("data_as_of", "2026-10-04T20:20:21Z")])
    connection.commit()
    connection.close()
    osm = LocalOSM(path)
    yield osm
    osm.close()


def test_road_is_measured_to_its_geometry_not_its_midpoint(store) -> None:
    hit = store.nearest(*ORIGIN, "road")
    assert hit["name"] == "Long Road"
    assert 15 < hit["distance_m"] < 30, hit
    assert hit["class"] == "primary"
    assert hit["tags"] == {"surface": "asphalt"}
    # The reported point lies on the road, beside the origin.
    assert abs(hit["lat"] - (ORIGIN[1] + 0.0002)) < 1e-5
    assert abs(hit["lon"] - ORIGIN[0]) < 1e-5


def test_point_inside_a_polygon_is_zero_distance(store) -> None:
    assert store.nearest(*ORIGIN, "school")["distance_m"] == 0.0


def test_class_filter_skips_nearer_features_of_other_classes(store) -> None:
    drain = store.nearest(*ORIGIN, "waterway")
    river = store.nearest(*ORIGIN, "waterway", {"river", "canal"})
    assert drain["class"] == "drain" and drain["distance_m"] < 250
    assert river["name"] == "Palar" and 2700 < river["distance_m"] < 2800


def test_search_widens_but_stops_at_the_limit(store) -> None:
    hit = store.nearest(*ORIGIN, "hospital")  # ~4.3 km away, found after widening
    assert 4200 < hit["distance_m"] < 4400
    assert store.nearest(*ORIGIN, "hospital", max_distance_m=3000) is None
    assert store.nearest(*ORIGIN, "rail_station") is None


def test_store_is_read_only(store) -> None:
    with pytest.raises(Exception):
        store.connection.execute("DELETE FROM features")


def test_missing_store_is_reported(tmp_path) -> None:
    with pytest.raises(LocalDataMissing):
        LocalOSM(tmp_path / "absent.sqlite")
    with pytest.raises(LocalDataMissing):
        Coverage.load(tmp_path)


def test_outside_parcel_runs_no_collector(monkeypatch) -> None:
    """Outside coverage must stop before any evidence provider is called."""
    import etl_pipeline

    monkeypatch.setattr(etl_pipeline, "coverage", lambda: COVERAGE)

    def explode(*_args, **_kwargs):
        raise AssertionError("a collector ran for a parcel outside coverage")

    monkeypatch.setattr(etl_pipeline, "get_satellite_client", explode)
    monkeypatch.setattr(etl_pipeline, "LocalOSM", explode)
    monkeypatch.setattr(etl_pipeline.InfrastructureClient, "nearest_amenities", explode)
    with pytest.raises(etl_pipeline.OutsideCoverage) as caught:
        etl_pipeline.build_evidence_snapshot(_parcel(73.85, 18.52), "2025-01-01", "2026-01-01")
    assert caught.value.result["status"] == "outside"
