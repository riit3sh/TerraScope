"""Unit tests for the Sentinel-2 observation path (no network)."""

from __future__ import annotations

import sqlite3
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date

import numpy as np
import pytest

from connectors import satellite_planetary
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


# --- result cache (no network) ------------------------------------------------

POLYGON = {"type": "Polygon", "coordinates": [[[78.844, 14.450], [78.845, 14.450], [78.845, 14.452],
                                               [78.844, 14.452], [78.844, 14.450]]]}


def _scene(day: int, tile: str = "A") -> dict:
    return {"id": f"S2_2026-01-{day:02d}_{tile}", "properties": {"datetime": f"2026-01-{day:02d}T05:00:00Z",
                                                                 "eo:cloud_cover": 5.0}}


class _Fake:
    """Counts catalogue searches and scene reads; scenes in `cloudy` are unusable, in `broken` fail."""

    def __init__(self, monkeypatch, client, scenes, cloudy=(), broken=()):
        self.searches, self.reads = 0, []
        self.scenes, self.cloudy, self.broken = scenes, set(cloudy), set(broken)

        def search(_polygon, _start, _end):
            self.searches += 1
            return list(self.scenes)

        def observation(item, _geometry, _token):
            self.reads.append(item["id"])
            if item["id"] in self.broken:
                raise RuntimeError("Read failed")
            if item["id"] in self.cloudy:
                return None
            return {"date": item["properties"]["datetime"][:10], "ndvi": 0.3, "ndbi": -0.1, "usable_pixel_count": 9,
                    "scene_id": item["id"]}

        monkeypatch.setattr(client, "_search", search)
        monkeypatch.setattr(client, "_observation", observation)
        monkeypatch.setattr(client, "_sas_token", lambda: "token")


@pytest.fixture()
def cache_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("TERRASCOPE_DATA_DIR", str(tmp_path))
    monkeypatch.delenv("SENTINEL_CACHE", raising=False)
    return tmp_path


def test_second_identical_request_reads_nothing_and_returns_the_same_series(cache_dir, monkeypatch):
    client = PlanetaryComputerClient()
    fake = _Fake(monkeypatch, client, [_scene(d) for d in range(1, 6)])
    first = client.get_change_series(POLYGON, "2026-01-01", "2026-01-31")
    assert len(fake.reads) == 5 and fake.searches == 1
    second = client.get_change_series(POLYGON, "2026-01-01", "2026-01-31")
    assert second == first
    assert len(fake.reads) == 5 and fake.searches == 1  # catalogue and scenes both reused
    assert client.last_diagnostics["scenes_from_cache"] == 5
    assert client.last_diagnostics["catalogue_age_s"] is not None


def test_failed_reads_are_never_cached_but_unusable_scenes_are(cache_dir, monkeypatch):
    client = PlanetaryComputerClient()
    fake = _Fake(monkeypatch, client, [_scene(d) for d in range(1, 6)],
                 cloudy={"S2_2026-01-02_A"}, broken={"S2_2026-01-03_A"})
    client.get_change_series(POLYGON, "2026-01-01", "2026-01-31")
    assert client.last_diagnostics["observations_failed"] == 1
    assert client.last_diagnostics["observations_rejected"] == 1
    fake.reads.clear()
    fake.broken.clear()
    series = client.get_change_series(POLYGON, "2026-01-01", "2026-01-31")
    assert fake.reads == ["S2_2026-01-03_A"]  # only the failed scene is read again
    assert [row["scene_id"] for row in series] == ["S2_2026-01-01_A", "S2_2026-01-03_A", "S2_2026-01-04_A",
                                                    "S2_2026-01-05_A"]
    assert client.last_diagnostics["observations_rejected"] == 1  # the cloudy one, from cache


def test_recent_catalogue_is_refreshed_so_new_scenes_appear(cache_dir, monkeypatch):
    client = PlanetaryComputerClient()
    fake = _Fake(monkeypatch, client, [_scene(1)])
    today = date.today().isoformat()
    client.get_change_series(POLYGON, "2026-01-01", today)
    fake.scenes.append(_scene(2))  # published later
    frozen = time.time()
    monkeypatch.setattr(satellite_planetary.time, "time", lambda: frozen + satellite_planetary.CATALOGUE_TTL_RECENT_S + 1)
    series = client.get_change_series(POLYGON, "2026-01-01", today)
    assert fake.searches == 2 and len(series) == 2
    assert client.last_diagnostics["catalogue_age_s"] is None  # queried live


def test_historical_catalogue_is_kept_longer(cache_dir, monkeypatch):
    client = PlanetaryComputerClient()
    fake = _Fake(monkeypatch, client, [_scene(1)])
    client.get_change_series(POLYGON, "2025-01-01", "2025-06-30")
    frozen = time.time()
    monkeypatch.setattr(satellite_planetary.time, "time", lambda: frozen + satellite_planetary.CATALOGUE_TTL_RECENT_S + 1)
    client.get_change_series(POLYGON, "2025-01-01", "2025-06-30")
    assert fake.searches == 1


def test_cache_keys_cover_polygon_dates_and_algorithm(cache_dir, monkeypatch):
    client = PlanetaryComputerClient()
    fake = _Fake(monkeypatch, client, [_scene(1)])
    client.get_change_series(POLYGON, "2026-01-01", "2026-01-31")
    moved = {"type": "Polygon", "coordinates": [[[x + 0.0001, y] for x, y in POLYGON["coordinates"][0]]]}
    client.get_change_series(moved, "2026-01-01", "2026-01-31")
    client.get_change_series(POLYGON, "2026-01-01", "2026-01-30")
    assert fake.searches == 3 and len(fake.reads) == 2  # new polygon re-reads; new dates re-search
    monkeypatch.setattr(satellite_planetary, "ALGORITHM_VERSION", "next")
    client.get_change_series(POLYGON, "2026-01-01", "2026-01-31")
    assert len(fake.reads) == 3


def test_cache_can_be_switched_off(cache_dir, monkeypatch):
    monkeypatch.setenv("SENTINEL_CACHE", "off")
    client = PlanetaryComputerClient()
    fake = _Fake(monkeypatch, client, [_scene(1)])
    client.get_change_series(POLYGON, "2026-01-01", "2026-01-31")
    client.get_change_series(POLYGON, "2026-01-01", "2026-01-31")
    assert fake.searches == 2 and not (cache_dir / "satellite").exists()


def test_cache_is_bounded_and_safe_for_concurrent_writers(cache_dir, monkeypatch):
    monkeypatch.setitem(satellite_planetary.CACHE_MAX_ROWS, "scenes", 50)
    cache = satellite_planetary.ResultCache(cache_dir / "c.sqlite")
    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(lambda i: cache.put("scenes", f"k{i}", {"i": i}), range(200)))
    cache.get("scenes", "k0")  # recently used: survives eviction
    cache.prune()
    with sqlite3.connect(cache.path) as db:
        assert db.execute("SELECT COUNT(*) FROM scenes").fetchone()[0] == 50
    assert cache.get("scenes", "k0") is not None
