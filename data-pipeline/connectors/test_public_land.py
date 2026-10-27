"""Public facilities near a parcel: overlap vs proximity, on a synthetic store (no real records, no network)."""

import json
from datetime import datetime, timezone

from shapely.geometry import LineString, Point, box, mapping

from connectors import public_land
from connectors.local_osm import create_store, write_features

NOW = datetime(2026, 10, 26, tzinfo=timezone.utc)
LON, LAT = 80.2000, 13.0000
M = 1 / 111_000  # roughly one metre in degrees here
PARCEL = mapping(box(LON, LAT, LON + 50 * M, LAT + 50 * M))  # about 50 m x 50 m


def store(tmp_path, features, as_of="2026-10-04T00:00:00Z"):
    path = tmp_path / public_land.STORE_NAME
    connection = create_store(path)
    write_features(connection, features)
    connection.executemany("INSERT INTO store_meta VALUES (?, ?)",
                           [("source", "synthetic test store"), ("data_as_of", as_of), ("licence", "test")])
    connection.commit()
    connection.close()
    return path


def test_a_parcel_overlapping_a_mapped_high_court_is_an_overlap_not_an_owner(tmp_path) -> None:
    court = box(LON - 100 * M, LAT - 100 * M, LON + 30 * M, LAT + 30 * M)
    result = public_land.assess(PARCEL, store(tmp_path, [("court", "courthouse", "High Court", "w1", {"amenity": "courthouse"}, court)]), now=NOW)
    hit = result["overlaps"][0]
    assert result["status"] == "assessed" and hit["category"] == "court" and hit["contact"] == "overlap"
    assert 0.3 < hit["overlap_share"] < 0.4 and hit["ownership_signal"] == "unknown", "a court tag is not an ownership record"
    assert result["authoritative_boundaries"] is None


def test_a_stadium_overlap_keeps_its_ownership_unknown(tmp_path) -> None:
    stadium = box(LON + 40 * M, LAT, LON + 200 * M, LAT + 200 * M)
    result = public_land.assess(PARCEL, store(tmp_path, [("sports", "stadium", "City Stadium", "w2", {"leisure": "stadium"}, stadium)]), now=NOW)
    hit = result["overlaps"][0]
    assert hit["contact"] == "overlap" and hit["category_label"].startswith("Stadium")
    assert hit["ownership_signal"] == "unknown" and "geometry" in hit


def test_a_parcel_near_a_stadium_but_outside_it_is_only_nearby(tmp_path) -> None:
    stadium = box(LON + 150 * M, LAT, LON + 300 * M, LAT + 100 * M)  # about 100 m east of the plot
    result = public_land.assess(PARCEL, store(tmp_path, [("sports", "stadium", "City Stadium", "w3", {"leisure": "stadium"}, stadium)]), now=NOW)
    assert result["overlaps"] == [] and result["nearby"][0]["contact"] == "nearby"
    assert 80 < result["nearby"][0]["distance_m"] < 120


def test_a_feature_within_the_positional_uncertainty_is_an_edge_contact(tmp_path) -> None:
    park = box(LON + 58 * M, LAT, LON + 120 * M, LAT + 50 * M)  # about 8 m away
    result = public_land.assess(PARCEL, store(tmp_path, [("park", "park", None, "w4", {}, park)]), now=NOW)
    assert result["overlaps"][0]["contact"] == "edge"


def test_a_railway_line_crossing_the_plot_and_a_point_facility_inside_it_are_flagged(tmp_path) -> None:
    track = LineString([(LON - 100 * M, LAT + 25 * M), (LON + 200 * M, LAT + 25 * M)])
    office = Point(LON + 10 * M, LAT + 10 * M)
    result = public_land.assess(PARCEL, store(tmp_path, [("railway_track", "rail", None, "w5", {}, track),
                                                         ("government_office", "police", "Police", "n6", {"amenity": "police"}, office)]), now=NOW)
    contacts = {i["category"]: i["contact"] for i in result["overlaps"]}
    assert contacts == {"railway_track": "overlap", "government_office": "point_inside"}


def test_missing_or_outdated_map_data_is_reported_never_read_as_private_land(tmp_path) -> None:
    missing = public_land.assess(PARCEL, tmp_path / "absent.sqlite", now=NOW)
    assert missing["status"] == "unavailable" and missing["overlaps"] == [] and "not built" in missing["reason"]
    old = public_land.assess(PARCEL, store(tmp_path, [], as_of="2023-01-01T00:00:00Z"), now=NOW)
    assert old["status"] == "assessed" and old["stale"] is True and old["overlaps"] == []
    assert "not proof that the land is private" in old["limitations"]


def test_classification_keeps_facility_type_apart_from_ownership() -> None:
    def kinds(tags, area=True):
        return [c for c, _ in public_land.classify(tags, area, False, False)]
    assert kinds({"leisure": "stadium"}) == ["sports"]
    assert kinds({"amenity": "school", "name": "Government Higher Secondary School"}) == ["government_school"]
    assert kinds({"amenity": "school", "name": "St. Mary's School"}) == [], "a private school is not a public facility"
    # Seen in Chennai: a private clinic tagged operator:type=public, and a swimming academy tagged sports_centre.
    assert kinds({"amenity": "hospital", "name": "Malar Clinic", "operator": "Dr. Arun", "operator:type": "public"}) == []
    assert kinds({"amenity": "hospital", "name": "Govt Hospital", "operator:type": "government"}) == ["government_hospital"]
    assert kinds({"leisure": "sports_centre", "name": "Waves Swimming Academy"}) == []
    assert kinds({"leisure": "sports_centre", "name": "Corporation Sports Centre"}) == ["sports"]
    assert public_land.ownership_signal({"operator:type": "public"}, "sports")[0] == "unknown"
    assert public_land.ownership_signal({"leisure": "stadium"}, "sports")[0] == "unknown"
    assert public_land.ownership_signal({"landuse": "military"}, "defence")[0] == "government_tagged"
    assert public_land.ownership_signal({"ownership": "private"}, "sports")[0] == "private_tagged"
    json.dumps(public_land.CATEGORIES)
