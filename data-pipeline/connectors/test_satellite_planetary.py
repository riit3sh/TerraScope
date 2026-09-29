"""Unit tests for the Sentinel-2 observation path (no network)."""

from __future__ import annotations

import numpy as np

from connectors.satellite_planetary import (
    MIN_USABLE_PIXELS,
    UNUSABLE_SCL,
    PlanetaryComputerClient,
)


def test_cloud_classes_are_excluded() -> None:
    """Cloud, shadow, cirrus, saturated and no-data must not enter a mean."""
    for scl_value in (0, 1, 3, 8, 9, 10):
        assert scl_value in UNUSABLE_SCL
    for clear_value in (4, 5, 6, 7):  # vegetation, bare soil, water, unclassified
        assert clear_value not in UNUSABLE_SCL


def test_bbox_comes_from_the_polygon_ring() -> None:
    polygon = {"type": "Polygon", "coordinates": [[[78.844, 14.450], [78.845, 14.450],
                                                   [78.845, 14.452], [78.844, 14.452],
                                                   [78.844, 14.450]]]}
    assert PlanetaryComputerClient._bbox(polygon) == [78.844, 14.450, 78.845, 14.452]


def test_observation_is_rejected_when_too_few_clear_pixels(monkeypatch) -> None:
    """A parcel mostly under cloud yields no observation rather than a biased mean."""
    client = PlanetaryComputerClient()
    red = np.ma.masked_array(np.full((4, 4), 2000), mask=False)
    nir = np.ma.masked_array(np.full((4, 4), 4000), mask=False)
    swir = np.ma.masked_array(np.full((4, 4), 3000), mask=False)
    # All but two pixels are cloud (9) - below MIN_USABLE_PIXELS.
    scl = np.ma.masked_array(np.full((4, 4), 9), mask=False)
    scl[0, 0] = 4
    scl[0, 1] = 4

    bands = {"B04": (red, 10.0), "B08": (nir, 10.0), "B11": (swir, 20.0), "SCL": (scl, 20.0)}
    monkeypatch.setattr(client, "_read_band", lambda item, band, geom, token: bands[band])
    item = {"id": "test", "properties": {"datetime": "2026-01-01T00:00:00Z", "eo:cloud_cover": 90}}
    assert MIN_USABLE_PIXELS > 2
    assert client._observation(item, {}, "tok") is None


def test_clear_scene_produces_expected_ndvi(monkeypatch) -> None:
    """NDVI must be (NIR - RED) / (NIR + RED) over the clear pixels."""
    client = PlanetaryComputerClient()
    red = np.ma.masked_array(np.full((4, 4), 2000.0), mask=False)
    nir = np.ma.masked_array(np.full((4, 4), 4000.0), mask=False)
    swir = np.ma.masked_array(np.full((4, 4), 3000.0), mask=False)
    scl = np.ma.masked_array(np.full((4, 4), 4), mask=False)  # all vegetation

    bands = {"B04": (red, 10.0), "B08": (nir, 10.0), "B11": (swir, 20.0), "SCL": (scl, 20.0)}
    monkeypatch.setattr(client, "_read_band", lambda item, band, geom, token: bands[band])
    item = {"id": "s2", "properties": {"datetime": "2026-06-28T05:12:41Z", "eo:cloud_cover": 10.9}}
    observation = client._observation(item, {}, "tok")

    assert observation is not None
    assert observation["ndvi"] == round((4000 - 2000) / (4000 + 2000), 4)
    assert observation["ndbi"] == round((3000 - 4000) / (3000 + 4000), 4)
    assert observation["usable_pixel_count"] == 16
    assert observation["date"] == "2026-06-28"
    assert observation["resolution_m"] == 10.0
    assert observation["parcel_cloud_fraction"] == 0.0


def test_scene_cloud_percentage_is_recorded_as_a_fraction(monkeypatch) -> None:
    client = PlanetaryComputerClient()
    ones = np.ma.masked_array(np.full((4, 4), 1000.0), mask=False)
    scl = np.ma.masked_array(np.full((4, 4), 5), mask=False)
    bands = {"B04": (ones, 10.0), "B08": (ones * 2, 10.0), "B11": (ones, 20.0), "SCL": (scl, 20.0)}
    monkeypatch.setattr(client, "_read_band", lambda item, band, geom, token: bands[band])
    item = {"id": "s2", "properties": {"datetime": "2026-06-28T05:12:41Z", "eo:cloud_cover": 34.9}}
    assert client._observation(item, {}, "tok")["cloud_coverage"] == 0.349


def test_client_is_not_flagged_as_demo() -> None:
    """The report distinguishes real imagery from the synthetic fallback."""
    client = PlanetaryComputerClient()
    assert client.is_demo is False
    assert "Sentinel-2" in client.source_reference
