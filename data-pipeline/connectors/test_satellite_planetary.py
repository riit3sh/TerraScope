"""Unit tests for the Sentinel-2 observation path (no network)."""

from __future__ import annotations

import sqlite3
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta

import numpy as np
import pytest
from affine import Affine

from connectors import satellite_planetary
from connectors.satellite_planetary import (
    MIN_USABLE_PIXELS,
    UNUSABLE_SCL,
    PlanetaryComputerClient,
    season_anchors,
)

GRID = Affine(10.0, 0.0, 500000.0, 0.0, -10.0, 1500000.0)


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


def _bands(monkeypatch, client, red, nir, swir, scl, footprint=None):
    full = footprint if footprint is not None else int((~np.ma.getmaskarray(red)).sum())
    monkeypatch.setattr(client, "_crop_grid", lambda item, geom, token: (GRID, red.shape))
    monkeypatch.setattr(client, "_read_band", lambda item, band, geom, token: ({"B04": red, "B08": nir}[band], GRID, full))
    monkeypatch.setattr(client, "_read_on_grid", lambda item, band, transform, shape, token: {"B11": swir, "SCL": scl}[band])


def _full(value):
    return np.ma.masked_array(np.full((4, 4), value, dtype=float), mask=False)


def _item(baseline="05.11", cloud=10.9, day="2026-06-28"):
    return {"id": "s2", "properties": {"datetime": f"{day}T05:12:41Z", "eo:cloud_cover": cloud,
                                       "s2:processing_baseline": baseline}}


def test_observation_is_rejected_when_too_few_clear_pixels(monkeypatch) -> None:
    """A parcel mostly under cloud yields no observation rather than a biased mean."""
    client = PlanetaryComputerClient()
    scl = np.full((4, 4), 9)
    scl[0, :2] = 4  # two clear pixels: below MIN_USABLE_PIXELS
    _bands(monkeypatch, client, _full(2000), _full(4000), np.full((4, 4), 3000.0), scl)
    assert MIN_USABLE_PIXELS > 2
    assert client._observation(_item(cloud=90), {}, "tok") is None


def test_indices_use_reflectance_after_the_baseline_offset(monkeypatch) -> None:
    """From processing baseline 04.00, DN = 10000*rho + 1000; the offset must come off before NDVI/NDBI."""
    client = PlanetaryComputerClient()
    _bands(monkeypatch, client, _full(1500), _full(4000), np.full((4, 4), 3000.0), np.full((4, 4), 4))
    observation = client._observation(_item(), {}, "tok")
    red, nir, swir = 500, 3000, 2000  # reflectance x 10000
    assert observation["ndvi"] == round((nir - red) / (nir + red), 4)
    assert observation["ndbi"] == round((swir - nir) / (swir + nir), 4)
    assert observation["reflectance_offset_dn"] == 1000
    assert observation["usable_pixel_count"] == 16 and observation["parcel_cloud_fraction"] == 0.0
    assert observation["cloud_coverage"] == 0.109 and observation["date"] == "2026-06-28"
    # An older baseline has no offset.
    assert client._observation(_item(baseline="03.01"), {}, "tok")["ndvi"] == round((4000 - 1500) / (4000 + 1500), 4)


def test_swir_is_averaged_over_clear_pixels_only(monkeypatch) -> None:
    """v1 averaged B11 over cloud as well; a bright cloud pixel must not move NDBI."""
    client = PlanetaryComputerClient()
    swir = np.full((4, 4), 3000.0)
    swir[0, 0] = 9000.0
    scl = np.full((4, 4), 4)
    scl[0, 0] = 9  # that pixel is cloud
    _bands(monkeypatch, client, _full(1500), _full(4000), swir, scl)
    assert client._observation(_item(), {}, "tok")["ndbi"] == round((2000 - 3000) / (2000 + 3000), 4)


def test_pixels_outside_the_parcel_are_ignored(monkeypatch) -> None:
    client = PlanetaryComputerClient()
    outside = np.zeros((4, 4), dtype=bool)
    outside[:, 2:] = True
    red = np.ma.masked_array(np.full((4, 4), 1500.0), mask=outside)
    nir = np.ma.masked_array(np.where(outside, 9999.0, 4000.0), mask=outside)
    _bands(monkeypatch, client, red, nir, np.full((4, 4), 3000.0), np.full((4, 4), 4))
    observation = client._observation(_item(), {}, "tok")
    assert observation["usable_pixel_count"] == 8 and observation["parcel_pixel_count"] == 8
    assert observation["ndvi"] == round((3000 - 500) / (3000 + 500), 4)


def test_a_tile_edge_cutting_the_parcel_is_not_a_clear_view(monkeypatch) -> None:
    """Regression (VIT): tile T44PLV covered 36 of the parcel's 134 pixels and was counted as 0% cloud."""
    client = PlanetaryComputerClient()
    _bands(monkeypatch, client, _full(1500), _full(4000), np.full((4, 4), 3000.0), np.full((4, 4), 4), footprint=60)
    observation = client._observation(_item(), {}, "tok")
    assert observation["parcel_pixel_count"] == 60 and observation["scene_covers_fraction"] == round(16 / 60, 3)
    assert observation["parcel_cloud_fraction"] == round(1 - 16 / 60, 3)
    assert not client._usable(observation)


def test_scenes_whose_footprint_misses_part_of_the_parcel_are_skipped(cache_dir, monkeypatch):
    client = PlanetaryComputerClient()
    scenes = _every_five_days()
    clipping = {"type": "Polygon", "coordinates": [[[78.8445, 14.0], [80.0, 14.0], [80.0, 15.0], [78.8445, 15.0], [78.8445, 14.0]]]}
    for scene in scenes[::2]:
        scene["geometry"] = clipping  # these tiles end inside the parcel
    fake = _Fake(monkeypatch, client, scenes)
    client.get_change_series(POLYGON, START, END)
    assert not set(fake.reads) & {s["id"] for s in scenes[::2]}
    assert client.last_diagnostics["scenes_not_covering_parcel"] == len(scenes[::2])


def test_client_is_not_flagged_as_demo() -> None:
    """The report distinguishes real imagery from the synthetic fallback."""
    client = PlanetaryComputerClient()
    assert client.is_demo is False
    assert "Sentinel-2" in client.source_reference


# --- season anchors ------------------------------------------------------------

def test_two_year_window_gets_quarterly_anchors_with_same_season_partners() -> None:
    anchors, tolerance = season_anchors(date(2024, 10, 12), date(2026, 10, 12), 8)
    assert len(anchors) == 8 and tolerance == 30
    assert anchors[0] < date(2025, 1, 1)  # the start of the window is sampled
    for first_year, second_year in zip(anchors[:4], anchors[4:]):
        assert (second_year - first_year).days == 365


def test_short_window_gets_evenly_spaced_anchors() -> None:
    anchors, tolerance = season_anchors(date(2026, 1, 1), date(2026, 3, 1), 8)
    assert len(anchors) == 8 and anchors == sorted(anchors) and tolerance >= 3


# --- catalogue paging (no network) ------------------------------------------------

class _Response:
    def __init__(self, payload, status_code=200):
        self.payload = payload
        self.status_code = status_code

    def raise_for_status(self):
        pass

    def json(self):
        return self.payload


def _feature(day: str, scene: str):
    return {"id": scene, "properties": {"datetime": f"{day}T05:00:00Z", "eo:cloud_cover": 3.0},
            "assets": {band: {"href": f"https://x/{scene}/{band}.tif"} for band in ("B04", "B08", "B11", "SCL")}}


BOX = {"type": "Polygon", "coordinates": [[[79.1, 12.9], [79.2, 12.9], [79.2, 13.0], [79.1, 12.9]]]}


def test_every_catalogue_page_is_read(monkeypatch) -> None:
    """Regression: the API returns the newest 100 scenes per page; page 1 alone dropped the start of the window."""
    bodies = []

    def post(url, json, timeout):
        bodies.append(json)
        if "token" not in json:
            return _Response({"features": [_feature("2026-09-29", "new")],
                              "links": [{"rel": "next", "method": "POST", "href": url, "body": {**json, "token": "next:1"}}]})
        return _Response({"features": [_feature("2024-10-29", "old")], "links": [{"rel": "previous"}]})

    monkeypatch.setattr(satellite_planetary.requests, "post", post)
    features, truncated = PlanetaryComputerClient()._search(BOX, "2026-01-01", "2026-03-01")  # one slice
    assert [f["id"] for f in features] == ["old", "new"] and truncated is False
    assert bodies[0]["fields"] == satellite_planetary.STAC_FIELDS and bodies[1]["token"] == "next:1"


def test_catalogue_paging_is_bounded_and_says_so(monkeypatch) -> None:
    monkeypatch.setattr(satellite_planetary, "MAX_CATALOGUE_PAGES", 2)
    calls = []

    def post(url, json, timeout):
        calls.append(1)
        return _Response({"features": [_feature("2026-01-01", f"s{len(calls)}")],
                          "links": [{"rel": "next", "method": "POST", "href": url, "body": {**json, "token": "t"}}]})

    monkeypatch.setattr(satellite_planetary.requests, "post", post)
    features, truncated = PlanetaryComputerClient()._search(BOX, "2026-01-01", "2026-02-01")
    assert len(features) == 2 and truncated is True


def test_a_long_window_is_searched_as_slices_that_cover_it_exactly(monkeypatch) -> None:
    windows = []

    def post(url, json, timeout):
        windows.append(json["datetime"])
        day = json["datetime"][:10]
        return _Response({"features": [_feature(day, f"s{day}")], "links": []})

    monkeypatch.setattr(satellite_planetary.requests, "post", post)
    features, _ = PlanetaryComputerClient()._search(BOX, "2024-10-12", "2026-10-12")
    spans = sorted((w[:10], w.split("/")[1][:10]) for w in windows)
    assert spans[0][0] == "2024-10-12" and spans[-1][1] == "2026-10-12" and len(spans) == 4
    for (_, stop), (begin, _) in zip(spans, spans[1:]):  # contiguous, no day searched twice or skipped
        assert date.fromisoformat(begin) - date.fromisoformat(stop) == timedelta(days=1)
    assert [f["id"] for f in features] == sorted(f["id"] for f in features)


def test_a_gateway_timeout_is_retried(monkeypatch) -> None:
    monkeypatch.setattr(satellite_planetary.time, "sleep", lambda seconds: None)
    replies = [_Response({}, 504), _Response({"features": [_feature("2026-01-05", "a")], "links": []})]
    monkeypatch.setattr(satellite_planetary.requests, "post", lambda url, json, timeout: replies.pop(0))
    features, _ = PlanetaryComputerClient()._search(BOX, "2026-01-01", "2026-02-01")
    assert [f["id"] for f in features] == ["a"] and not replies


def test_a_failed_search_reuses_the_stored_listing(monkeypatch, tmp_path) -> None:
    cache = satellite_planetary.ResultCache(tmp_path / "c.sqlite")
    client = PlanetaryComputerClient()
    monkeypatch.setattr(client, "_search", lambda *a: ([_feature("2026-01-05", "a")], False))
    client._catalogue(cache, BOX, "2026-01-01", "2026-02-01")
    monkeypatch.setattr(satellite_planetary, "CATALOGUE_TTL_RECENT_S", -1)
    monkeypatch.setattr(satellite_planetary, "CATALOGUE_TTL_HISTORICAL_S", -1)

    def down(*a):
        raise satellite_planetary.requests.HTTPError("504 Server Error")

    monkeypatch.setattr(client, "_search", down)
    features, _, age = client._catalogue(cache, BOX, "2026-01-01", "2026-02-01")
    assert [f["id"] for f in features] == ["a"] and age is not None


# --- selection and result cache (no network) -----------------------------------------

POLYGON = {"type": "Polygon", "coordinates": [[[78.844, 14.450], [78.845, 14.450], [78.845, 14.452],
                                               [78.844, 14.452], [78.844, 14.450]]]}
START, END = "2024-10-12", "2026-10-12"


def _scene(day: date, tile: str = "A", cloud: float = 5.0) -> dict:
    return {"id": f"S2_{day.isoformat()}_{tile}", "properties": {"datetime": f"{day.isoformat()}T05:00:00Z",
                                                                 "eo:cloud_cover": cloud}}


def _every_five_days(start=date(2024, 10, 14), end=date(2026, 10, 10)):
    days, out = start, []
    while days <= end:
        out.append(_scene(days))
        days += timedelta(days=5)
    return out


class _Fake:
    """Counts catalogue searches and scene reads. `cloudy` scenes have too few clear pixels,
    `hazy` ones are clear on only 30% of the parcel, `broken` ones fail to read."""

    def __init__(self, monkeypatch, client, scenes, cloudy=(), hazy=(), broken=()):
        self.searches, self.reads = 0, []
        self.scenes, self.cloudy, self.hazy, self.broken = scenes, set(cloudy), set(hazy), set(broken)

        def search(_polygon, _start, _end):
            self.searches += 1
            return list(self.scenes), False

        def observation(item, _geometry, _token):
            self.reads.append(item["id"])
            if item["id"] in self.broken:
                raise RuntimeError("Read failed")
            if item["id"] in self.cloudy:
                return None
            return {"date": item["properties"]["datetime"][:10], "ndvi": 0.3, "ndbi": -0.1, "usable_pixel_count": 9,
                    "parcel_pixel_count": 10, "parcel_cloud_fraction": 0.7 if item["id"] in self.hazy else 0.1,
                    "scene_id": item["id"]}

        monkeypatch.setattr(client, "_search", search)
        monkeypatch.setattr(client, "_observation", observation)
        monkeypatch.setattr(client, "_sas_token", lambda: "token")


@pytest.fixture()
def cache_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("TERRASCOPE_DATA_DIR", str(tmp_path))
    monkeypatch.delenv("SENTINEL_CACHE", raising=False)
    return tmp_path


def _first_choices(monkeypatch, scenes):
    """The scenes picked on a cold run, without touching the shared cache."""
    monkeypatch.setenv("SENTINEL_CACHE", "off")
    client = PlanetaryComputerClient()
    fake = _Fake(monkeypatch, client, scenes)
    client.get_change_series(POLYGON, START, END)
    monkeypatch.delenv("SENTINEL_CACHE")
    return fake.reads


def test_one_observation_per_season_anchor_across_the_whole_window(cache_dir, monkeypatch):
    client = PlanetaryComputerClient()
    fake = _Fake(monkeypatch, client, _every_five_days())
    series = client.get_change_series(POLYGON, START, END)
    anchors = client.last_diagnostics["anchors"]
    assert len(series) == len(anchors) == 8 and len(fake.reads) == 8  # one wave, no alternates needed
    assert series[0]["date"] < "2025-01-01"
    for row in series:
        assert abs((date.fromisoformat(row["date"]) - date.fromisoformat(row["anchor_date"])).days) <= 30


def test_alternates_are_read_only_for_anchors_whose_first_choice_fails(cache_dir, monkeypatch):
    scenes = _every_five_days()
    first = _first_choices(monkeypatch, scenes)
    client = PlanetaryComputerClient()
    fake = _Fake(monkeypatch, client, scenes, hazy={first[0]})
    series = client.get_change_series(POLYGON, START, END)
    assert len(fake.reads) == 8 + satellite_planetary.ALTERNATES_PER_ANCHOR
    assert first[0] not in [row["scene_id"] for row in series] and len(series) == 8
    assert client.last_diagnostics["rejected_below_clear_fraction"] == 1


def test_second_identical_request_reads_nothing_and_returns_the_same_series(cache_dir, monkeypatch):
    client = PlanetaryComputerClient()
    fake = _Fake(monkeypatch, client, _every_five_days())
    first = client.get_change_series(POLYGON, START, END)
    second = client.get_change_series(POLYGON, START, END)
    assert second == first
    assert len(fake.reads) == 8 and fake.searches == 1  # catalogue and scenes both reused
    assert client.last_diagnostics["scenes_from_cache"] == 8
    assert client.last_diagnostics["catalogue_age_s"] is not None


def test_failed_reads_are_never_cached_but_unusable_scenes_are(cache_dir, monkeypatch):
    scenes = _every_five_days()
    picks = _first_choices(monkeypatch, scenes)
    client = PlanetaryComputerClient()
    fake = _Fake(monkeypatch, client, scenes, cloudy={picks[1]}, broken={picks[2]})
    client.get_change_series(POLYGON, START, END)
    assert client.last_diagnostics["observations_failed"] == 1
    assert client.last_diagnostics["rejected_too_few_clear_pixels"] == 1
    fake.reads.clear()
    fake.broken.clear()
    client.get_change_series(POLYGON, START, END)
    assert picks[2] in fake.reads and picks[1] not in fake.reads  # failed read retried; unusable one cached


def test_recent_catalogue_is_refreshed_so_new_scenes_appear(cache_dir, monkeypatch):
    client = PlanetaryComputerClient()
    today = date.today()
    window = ((today - timedelta(days=60)).isoformat(), today.isoformat())
    fake = _Fake(monkeypatch, client, [_scene(today - timedelta(days=45))])
    client.get_change_series(POLYGON, *window)
    fake.scenes.append(_scene(today - timedelta(days=5)))  # published later
    frozen = time.time()
    monkeypatch.setattr(satellite_planetary.time, "time", lambda: frozen + satellite_planetary.CATALOGUE_TTL_RECENT_S + 1)
    series = client.get_change_series(POLYGON, *window)
    assert fake.searches == 2 and len(series) == 2
    assert client.last_diagnostics["catalogue_age_s"] is None  # queried live


def test_historical_catalogue_is_kept_longer(cache_dir, monkeypatch):
    client = PlanetaryComputerClient()
    fake = _Fake(monkeypatch, client, [_scene(date(2025, 2, 1))])
    client.get_change_series(POLYGON, "2025-01-01", "2025-06-30")
    frozen = time.time()
    monkeypatch.setattr(satellite_planetary.time, "time", lambda: frozen + satellite_planetary.CATALOGUE_TTL_RECENT_S + 1)
    client.get_change_series(POLYGON, "2025-01-01", "2025-06-30")
    assert fake.searches == 1


def test_cache_keys_cover_polygon_dates_and_algorithm(cache_dir, monkeypatch):
    client = PlanetaryComputerClient()
    fake = _Fake(monkeypatch, client, [_scene(date(2026, 1, 15))])
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
    fake = _Fake(monkeypatch, client, [_scene(date(2026, 1, 15))])
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


def test_scene_reads_are_capped_across_concurrent_collections(cache_dir, monkeypatch):
    """Regression: timed-out collections kept reading and stacked up until the network saturated."""
    import threading
    monkeypatch.setenv("SENTINEL_CACHE", "off")
    monkeypatch.setattr(satellite_planetary, "_SCENE_SLOTS", threading.BoundedSemaphore(2))
    active, peak, lock = [0], [0], threading.Lock()

    def slow_observation(item, _geometry, _token):
        with lock:
            active[0] += 1
            peak[0] = max(peak[0], active[0])
        time.sleep(0.02)
        with lock:
            active[0] -= 1
        return {"date": item["properties"]["datetime"][:10], "ndvi": 0.3, "ndbi": -0.1, "usable_pixel_count": 9,
                "parcel_pixel_count": 10, "parcel_cloud_fraction": 0.1, "scene_id": item["id"]}

    clients = []
    for _ in range(3):
        client = PlanetaryComputerClient()
        _Fake(monkeypatch, client, _every_five_days())
        monkeypatch.setattr(client, "_observation", slow_observation)
        clients.append(client)
    with ThreadPoolExecutor(max_workers=3) as pool:
        list(pool.map(lambda c: c.get_change_series(POLYGON, START, END), clients))
    assert peak[0] == 2


def test_no_scene_read_starts_after_the_evidence_deadline(cache_dir, monkeypatch):
    """A collection past its deadline drops queued reads instead of reading on in the background."""
    client = PlanetaryComputerClient()
    fake = _Fake(monkeypatch, client, _every_five_days())
    client.give_up_at = time.monotonic() - 1
    with pytest.raises(satellite_planetary.SatelliteError):
        client.get_change_series(POLYGON, START, END)
    assert fake.reads == [] and client.last_diagnostics["observations_failed"] == 8
