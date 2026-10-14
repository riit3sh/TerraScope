"""Guard how road and school distances are measured.

`out center` reported a way's midpoint, so a long road running past the plot was
measured to its middle rather than to the point where it actually passes.
"""

from __future__ import annotations

from connectors.osm_infrastructure import InfrastructureClient


ORIGIN = (78.8445324, 14.4511446)  # (lon, lat) - the Kadapa pilot parcel centroid


def _way(*coords: tuple[float, float]) -> dict:
    return {"type": "way", "geometry": [{"lon": lon, "lat": lat} for lon, lat in coords]}


def test_long_way_is_measured_where_it_passes_not_at_its_midpoint() -> None:
    """A road hugging the parcel must not be pushed away by its own length."""
    lon, lat = ORIGIN
    # Runs due east from beside the parcel for roughly 2 km.
    way = _way((lon, lat + 0.0002), (lon + 0.02, lat + 0.0002))
    distance, point = InfrastructureClient._closest_point_on_element(ORIGIN, way)
    assert distance < 30, f"nearest point should be ~22 m away, got {distance:.0f} m"

    midpoint = {"type": "way", "center": {"lon": lon + 0.01, "lat": lat + 0.0002}}
    centre_distance, _ = InfrastructureClient._closest_point_on_element(ORIGIN, midpoint)
    assert centre_distance > 500, "the old midpoint method should be far off for this way"
    assert point[0] == lon or abs(point[0] - lon) < 1e-6


def test_distance_uses_the_segment_not_only_the_vertices() -> None:
    """The closest point can lie between two nodes."""
    lon, lat = ORIGIN
    way = _way((lon - 0.01, lat + 0.0002), (lon + 0.01, lat + 0.0002))
    distance, _ = InfrastructureClient._closest_point_on_element(ORIGIN, way)
    assert distance < 30, "a segment passing beside the origin must measure ~22 m"


def test_node_elements_still_work() -> None:
    lon, lat = ORIGIN
    node = {"type": "node", "lat": lat + 0.001, "lon": lon}
    distance, _ = InfrastructureClient._closest_point_on_element(ORIGIN, node)
    assert 100 < distance < 120


def test_element_without_usable_geometry_is_skipped() -> None:
    assert InfrastructureClient._closest_point_on_element(ORIGIN, {"type": "way"}) is None


def test_returned_point_lies_on_the_way() -> None:
    """The plotted marker must sit on the road, not at an invented offset."""
    lon, lat = ORIGIN
    way = _way((lon - 0.01, lat + 0.0002), (lon + 0.01, lat + 0.0002))
    _, (point_lon, point_lat) = InfrastructureClient._closest_point_on_element(ORIGIN, way)
    assert abs(point_lat - (lat + 0.0002)) < 1e-6, "point should lie on the way's latitude"
    assert lon - 0.01 <= point_lon <= lon + 0.01
