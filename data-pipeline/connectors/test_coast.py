"""Coastal relevance from a synthetic coastline: coastal, inland and missing data (no network, no real records)."""

import json

from shapely.geometry import LineString, box, mapping

from connectors import coast
from connectors.local_osm import create_store, write_features
from etl_pipeline import _coastal_component

M = 1 / 111_000  # roughly one metre in degrees near the equator
LON, LAT = 80.0, 13.0
SEA = LineString([(LON + 0.1, LAT - 0.5), (LON + 0.1, LAT + 0.5)])  # a north-south shore about 11 km east


def store(tmp_path):
    path = tmp_path / coast.STORE_NAME
    connection = create_store(path)
    write_features(connection, [("coastline", "coastline", None, "w1", {}, SEA)])
    connection.executemany("INSERT INTO store_meta VALUES (?, ?)", [("layers", json.dumps(["coastline"])), ("data_as_of", "2026-10-25")])
    connection.commit()
    connection.close()
    return path


def plot(lon):
    return mapping(box(lon, LAT, lon + 50 * M, LAT + 50 * M))


def test_a_plot_near_the_sea_is_coastal_and_still_not_assessed(tmp_path) -> None:
    near = coast.coast_distance(plot(LON + 0.1 - 2000 * M), store(tmp_path))
    assert near["coastal"] is True and 1900 < near["distance_m"] < 2100
    component = _coastal_component(near)
    assert component["status"] == "not_assessed" and "km from the sea" in component["summary"]


def test_an_inland_plot_makes_coastal_flooding_not_applicable(tmp_path) -> None:
    shore = store(tmp_path)
    far = coast.coast_distance(plot(LON - 0.5), shore)  # about 66 km inland: beyond the search window
    assert far["coastal"] is False and far["distance_m"] is None and far["beyond_m"] == coast.SEARCH_M
    assert _coastal_component(far)["status"] == "not_applicable"
    mid = coast.coast_distance(plot(LON), shore)  # about 11 km: beyond the 10 km band, within the search
    assert mid["coastal"] is False and _coastal_component(mid)["status"] == "not_applicable"


def test_a_missing_coastline_map_keeps_coastal_flooding_unknown(tmp_path) -> None:
    missing = coast.coast_distance(plot(LON), tmp_path / "absent.sqlite")
    assert missing["status"] == "unavailable"
    assert _coastal_component(missing)["status"] == "not_assessed", "unknown distance: never 'not applicable'"
