"""fetch_data --flood-tiles against a fake JRC server: tile selection, layout, resume, outage, offline read."""

from __future__ import annotations

import json

import numpy as np
import pytest
import rasterio
import requests
import shapely
from rasterio.transform import from_origin
from shapely.geometry import box, mapping

import fetch_data
from connectors import river_flood

RES = 1 / 1200
NEAR, FAR = "ID1_N13_E79", "ID2_N31_E85"


class FakeResponse:
    def __init__(self, status: int, body: bytes = b""):
        self.status_code, self.body = status, body
        self.ok = status < 400
        self.headers = {"Content-Length": str(len(body))} if self.ok else {}

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def raise_for_status(self):
        if not self.ok:
            raise requests.HTTPError(f"HTTP {self.status_code}")

    def iter_content(self, size):
        for start in range(0, len(self.body), size):
            yield self.body[start:start + size]


class FakeSession:
    """Serves `files` (path below BASE_URL -> bytes); with down=True every request times out, like 2026-10-28."""

    def __init__(self, files: dict[str, bytes], down: bool = False):
        self.files, self.down, self.requests = files, down, []

    def _answer(self, method, url, headers):
        self.requests.append((method, url))
        if self.down:
            raise requests.ReadTimeout("no bytes received")
        body = self.files.get(url.removeprefix(river_flood.BASE_URL + "/"))
        if body is None:
            return FakeResponse(404)
        if headers and "Range" in headers:
            return FakeResponse(206, body[:1024])
        return FakeResponse(200, body)

    def get(self, url, headers=None, **_):
        return self._answer("GET", url, headers)

    def head(self, url, headers=None, **_):
        return self._answer("HEAD", url, None)


def _tif_bytes(tmp_path, name, array, nodata, dtype) -> bytes:
    path = tmp_path / "src" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    with rasterio.open(path, "w", driver="GTiff", width=array.shape[1], height=array.shape[0], count=1, dtype=dtype,
                       crs="EPSG:4326", transform=from_origin(79.0, 13.0, RES, RES), nodata=nodata) as dst:
        dst.write(array.astype(dtype), 1)
    return path.read_bytes()


@pytest.fixture()
def server(tmp_path, monkeypatch):
    """Data root with an India outline over tile NEAR only, a two-tile index, and a fake server holding both tiles.

    NEAR's depth layers flood columns 20-39 by 1 m in every scenario; FAR's files are placeholders."""
    root = tmp_path / "data"
    monkeypatch.setenv("TERRASCOPE_DATA_DIR", str(root))
    monkeypatch.setattr(river_flood, "_index", None)
    monkeypatch.setattr(fetch_data.time, "sleep", lambda _: None)
    india = box(79.0, 12.8, 79.2, 13.0)
    (root / "india").mkdir(parents=True)
    (root / "india" / "india_boundary.wkb").write_bytes(shapely.to_wkb(india))
    (root / "india" / "india_states.geojson").write_text(json.dumps({"type": "FeatureCollection", "features": [
        {"type": "Feature", "properties": {"shapeISO": "IN-AA", "shapeName": "Near State"}, "geometry": mapping(india)},
        {"type": "Feature", "properties": {"shapeISO": "IN-BB", "shapeName": "Far State"},
         "geometry": mapping(box(85.2, 30.2, 85.4, 30.4))},
    ]}))
    (root / "flood-hazard").mkdir()
    (root / "flood-hazard" / "tile_extents.geojson").write_text(json.dumps({"type": "FeatureCollection", "features": [
        {"type": "Feature", "properties": {"id": 1, "name": "N13_E79"}, "geometry": mapping(box(79, 3, 89, 13))},
        {"type": "Feature", "properties": {"id": 2, "name": "N31_E85"}, "geometry": mapping(box(85, 30, 86, 31))},
    ]}))
    depth = np.full((240, 240), -9999.0)
    depth[:, 20:40] = 1.0
    files = {}
    for layer in river_flood.LAYERS:
        if layer.startswith("RP"):
            body = _tif_bytes(tmp_path, f"{layer}.tif", depth, -9999.0, "float32")
        else:
            body = _tif_bytes(tmp_path, f"{layer}.tif", np.full((240, 240), 255), 255, "uint8")
        files[river_flood.layer_relative_path(NEAR, layer)] = body
        files[river_flood.layer_relative_path(FAR, layer)] = f"far {layer}".encode()
    return root, files


def test_downloads_india_tiles_in_reader_layout_and_assess_reads_them_offline(server, monkeypatch):
    root, files = server
    session = FakeSession(files)
    manifest = fetch_data.fetch_flood_tiles(None, root, session)

    tiles = root / "flood-hazard" / "tiles"
    expected = {f"RP{rp}/{NEAR}_RP{rp}_depth.tif" for rp in river_flood.RETURN_PERIODS} | {
        f"Permanent_WaterBodies/{NEAR}_permanent_water.tif", f"Spurious_Depths/{NEAR}_spurious_depth_areas.tif"}
    on_disk = {path.relative_to(tiles).as_posix() for path in tiles.rglob("*.tif")}
    assert on_disk == expected
    assert all((tiles / relative).read_bytes() == files[relative] for relative in expected)
    assert not list(tiles.rglob("*.part"))
    assert not any(FAR in url for _, url in session.requests)
    assert manifest["tiles"] == [NEAR] and manifest["files"] == 9
    assert manifest["size_bytes"] == sum(len(files[relative]) for relative in expected)

    # The reader now finds every layer on disk; any network access fails the test.
    def no_network(*args, **kwargs):
        raise AssertionError("river_flood used the network")

    monkeypatch.setattr(river_flood.requests, "get", no_network)
    monkeypatch.setattr(river_flood, "_check_provider", no_network)
    assert all(not river_flood._layer_path(NEAR, layer).startswith("/vsicurl/") for layer in river_flood.LAYERS)
    lon0, lat0 = 79.0 + 20 * RES, 13.0 - 10 * RES  # 20 x 10 flooded cells
    parcel = mapping(box(lon0, lat0 - 10 * RES, lon0 + 20 * RES, lat0))
    result = river_flood.assess(parcel)
    assert result["status"] == "assessed" and result["errors"] is None
    assert all(s["flooded_share_of_parcel"] == pytest.approx(1.0, abs=1e-3) for s in result["scenarios"])


def test_region_selects_only_its_tiles(server):
    root, files = server
    session = FakeSession(files)
    manifest = fetch_data.fetch_flood_tiles("far-state", root, session)
    assert manifest["tiles"] == [FAR]
    assert not any(NEAR in url for _, url in session.requests)


def test_rerun_skips_complete_files_and_replaces_a_stale_part(server):
    root, files = server
    tiles = root / "flood-hazard" / "tiles"
    complete = tiles / river_flood.layer_relative_path(NEAR, "RP10")
    complete.parent.mkdir(parents=True)
    complete.write_bytes(b"already complete")
    interrupted = tiles / river_flood.layer_relative_path(NEAR, "RP20")
    interrupted.parent.mkdir(parents=True)
    (interrupted.parent / (interrupted.name + ".part")).write_bytes(b"trunc")

    session = FakeSession(files)
    fetch_data.fetch_flood_tiles(None, root, session)
    assert complete.read_bytes() == b"already complete"
    assert not any(url.endswith(complete.name) for _, url in session.requests)
    assert interrupted.read_bytes() == files[river_flood.layer_relative_path(NEAR, "RP20")]
    assert not list(tiles.rglob("*.part"))

    again = FakeSession(files)
    fetch_data.fetch_flood_tiles(None, root, again)
    assert again.requests == []


def test_unreachable_server_stops_before_downloading(server):
    root, files = server
    session = FakeSession(files, down=True)
    with pytest.raises(SystemExit, match="JRC flood hazard server is not responding"):
        fetch_data.fetch_flood_tiles(None, root, session)
    assert len(session.requests) == 1  # one probe, no retries or downloads
    assert not (root / "flood-hazard" / "tiles").exists() or not any((root / "flood-hazard" / "tiles").rglob("*"))


def test_missing_index_is_not_fetched_from_an_unreachable_server(server):
    root, files = server
    (root / "flood-hazard" / "tile_extents.geojson").unlink()
    with pytest.raises(SystemExit, match="not responding"):
        fetch_data.fetch_flood_tiles(None, root, FakeSession(files, down=True))
    assert not (root / "flood-hazard" / "tile_extents.geojson").exists()
