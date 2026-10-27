"""Local OpenStreetMap queries on small synthetic stores (coverage tests: test_regions.py)."""

from __future__ import annotations

import pytest
from shapely.geometry import LineString, Point, Polygon

from connectors.local_osm import LocalOSM, create_store, write_features
from connectors.regions import LocalDataMissing


def _parcel(lon: float, lat: float, size: float = 0.001) -> dict:
    return {"type": "Polygon", "coordinates": [[
        [lon, lat], [lon + size, lat], [lon + size, lat + size], [lon, lat + size], [lon, lat],
    ]]}


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


def test_a_store_without_roads_reports_them_not_installed_never_none_mapped(tmp_path) -> None:
    """The all-India store has no roads (2026-10-26): road distance must be unknown, not 'none within 5 km'."""
    import json

    from etl_pipeline import _local_amenities, _local_infrastructure_summary

    lon, lat = ORIGIN
    path = tmp_path / "national.sqlite"
    connection = create_store(path)
    write_features(connection, [("school", "school", "School", "n1", {}, Point(lon + 0.001, lat))])
    connection.executemany("INSERT INTO store_meta VALUES (?, ?)",
                           [("layers", json.dumps(["waterway", "school", "hospital", "bus", "rail_station", "water"]))])
    connection.commit()
    connection.close()
    osm = LocalOSM(path)
    try:
        assert not osm.has_layer("road") and osm.has_layer("school")
        amenities = _local_amenities(osm, _parcel(lon, lat))
    finally:
        osm.close()
    assert amenities["layer_status"]["road"] == "not_installed" and amenities["nearest_road_distance_m"] is None
    assert amenities["nearest_school_distance_m"] is not None
    assert "road data not installed" in _local_infrastructure_summary(amenities)

    # With the all-India road store, the road comes from it and everything else still from the regional store.
    roads_path = tmp_path / "roads.sqlite"
    connection = create_store(roads_path)
    write_features(connection, [("road", "primary", "NH 44", "w1", {}, LineString([(lon + 0.002, lat - 0.01), (lon + 0.002, lat + 0.01)]))])
    connection.executemany("INSERT INTO store_meta VALUES (?, ?)", [("layers", json.dumps(["road"]))])
    connection.commit()
    connection.close()
    osm, roads = LocalOSM(path), LocalOSM(roads_path)
    try:
        amenities = _local_amenities(osm, _parcel(lon, lat), roads)
    finally:
        osm.close()
        roads.close()
    assert amenities["layer_status"]["road"] == "installed" and amenities["nearest_road_name"] == "NH 44"
    assert 150 < amenities["nearest_road_distance_m"] < 250 and amenities["nearest_school_distance_m"] is not None


def test_stores_built_before_layer_lists_hold_every_layer(store) -> None:
    assert store.layers is None and store.has_layer("road")


def test_amenities_with_layer_status_pass_the_evidence_schema(tmp_path) -> None:
    """Regression (2026-10-26): the schema rejected layer_status, so every new analysis failed with HTTP 400."""
    import json
    from pathlib import Path

    import jsonschema

    from etl_pipeline import _local_amenities

    lon, lat = ORIGIN
    path = tmp_path / "national.sqlite"
    connection = create_store(path)
    connection.executemany("INSERT INTO store_meta VALUES (?, ?)", [("layers", json.dumps(["school", "water"]))])
    connection.commit()
    connection.close()
    osm = LocalOSM(path)
    try:
        amenities = _local_amenities(osm, _parcel(lon, lat))
    finally:
        osm.close()
    schema = json.loads((Path(__file__).resolve().parents[2] / "docs" / "schema" / "parcel_schema.json").read_text(encoding="utf-8"))
    jsonschema.validate(amenities, {**schema["properties"]["infrastructure"], "$defs": schema.get("$defs", {}),
                                    "definitions": schema.get("definitions", {})})
