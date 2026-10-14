"""JRC river flood hazard connector on synthetic tiles: no-data, zero depth, flags, failures, cache."""

from __future__ import annotations

import json

import numpy as np
import pytest
import rasterio
from rasterio.transform import from_origin

from connectors import river_flood

RES = 1 / 1200  # 3 arc-seconds, like the JRC maps
WEST, NORTH = 79.0, 13.0
PREFIX = "ID1_N13_E79"


def _tif(path, array, nodata, dtype):
    path.parent.mkdir(parents=True, exist_ok=True)
    with rasterio.open(path, "w", driver="GTiff", width=array.shape[1], height=array.shape[0], count=1, dtype=dtype,
                       crs="EPSG:4326", transform=from_origin(WEST, NORTH, RES, RES), nodata=nodata) as dst:
        dst.write(array.astype(dtype), 1)


def _cells(col0, row0, cols, rows):
    """Polygon exactly covering a block of pixels."""
    lon0, lat0 = WEST + col0 * RES, NORTH - row0 * RES
    lon1, lat1 = lon0 + cols * RES, lat0 - rows * RES
    return {"type": "Polygon", "coordinates": [[[lon0, lat1], [lon1, lat1], [lon1, lat0], [lon0, lat0], [lon0, lat1]]]}


@pytest.fixture()
def tiles(tmp_path, monkeypatch):
    """A 1x1 degree tile: columns 0-9 no-data, 10-19 valid zero depth, 20-29 flooded 0.5-2 m,
    30-39 permanent water (depth 1 m), 40-49 flooded 15 m inside a spurious-depth area."""
    monkeypatch.setenv("TERRASCOPE_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(river_flood, "_index", None)
    size = 1200
    root = tmp_path / "flood-hazard"
    root.mkdir()
    (root / "tile_extents.geojson").write_text(json.dumps({"type": "FeatureCollection", "features": [{
        "type": "Feature", "properties": {"id": 1, "name": "N13_E79"},
        "geometry": {"type": "Polygon", "coordinates": [[[79, 12], [80, 12], [80, 13], [79, 13], [79, 12]]]},
    }]}))
    permanent = np.full((size, size), 255)
    permanent[:, 30:40] = 1
    spurious = np.full((size, size), 255)
    spurious[:, 40:50] = 1
    for rp in river_flood.RETURN_PERIODS:
        depth = np.full((size, size), -9999.0)
        depth[:, 10:20] = 0.0
        # Deeper with rarer scenarios; nothing floods in the 1-in-10 scenario.
        depth[:, 20:30] = 0.0 if rp == 10 else min(2.0, 0.5 + rp / 400)
        depth[:, 30:40] = 1.0
        depth[:, 40:50] = 15.0
        _tif(root / "tiles" / f"RP{rp}" / f"{PREFIX}_RP{rp}_depth.tif", depth, -9999.0, "float32")
    _tif(root / "tiles" / "Permanent_WaterBodies" / f"{PREFIX}_permanent_water.tif", permanent, 255, "uint8")
    _tif(root / "tiles" / "Spurious_Depths" / f"{PREFIX}_spurious_depth_areas.tif", spurious, 255, "uint8")
    return tmp_path


def _scenario(result, rp):
    return next(s for s in result["scenarios"] if s["return_period_years"] == rp)


def test_no_data_is_not_counted_as_dry_or_flooded(tiles) -> None:
    result = river_flood.assess(_cells(0, 100, 10, 10))
    assert result["status"] == "assessed"
    rp100 = _scenario(result, 100)
    assert rp100["flooded_area_m2"] == 0
    assert rp100["zero_depth_area_m2"] == 0  # nodata is not a valid zero
    assert rp100["no_modelled_inundation_area_m2"] == pytest.approx(result["parcel_area_m2"], rel=1e-3)
    assert rp100["max_depth_m"] is None


def test_valid_zero_depth_is_reported_separately(tiles) -> None:
    rp100 = _scenario(river_flood.assess(_cells(10, 100, 10, 10)), 100)
    assert rp100["zero_depth_area_m2"] > 0 and rp100["flooded_area_m2"] == 0
    assert rp100["no_modelled_inundation_area_m2"] == 0


def test_flooded_cells_give_depth_by_scenario(tiles) -> None:
    result = river_flood.assess(_cells(15, 100, 10, 10))  # half zero-depth, half flooded
    assert _scenario(result, 10)["flooded_area_m2"] == 0
    rp100 = _scenario(result, 100)
    assert rp100["flooded_share_of_parcel"] == pytest.approx(0.5, abs=0.01)
    assert rp100["max_depth_m"] == pytest.approx(0.75, abs=0.01)
    assert _scenario(result, 500)["max_depth_m"] == pytest.approx(1.75, abs=0.01)


def test_permanent_water_is_excluded_from_flood_exposure(tiles) -> None:
    result = river_flood.assess(_cells(30, 100, 10, 10))
    assert result["permanent_water_area_m2"] == pytest.approx(result["parcel_area_m2"], rel=1e-3)
    assert _scenario(result, 100)["flooded_area_m2"] == 0


def test_quality_flagged_depths_are_withheld(tiles) -> None:
    result = river_flood.assess(_cells(40, 100, 10, 10))
    rp100 = _scenario(result, 100)
    assert result["quality_flagged_area_m2"] == pytest.approx(result["parcel_area_m2"], rel=1e-3)
    assert rp100["flagged_flooded_area_m2"] == pytest.approx(rp100["flooded_area_m2"], rel=1e-3)
    assert rp100["max_depth_m"] is None  # the 15 m artefact is never reported as a depth


def test_unmodelled_location_is_not_reported_as_safe(tiles) -> None:
    far_away = {"type": "Polygon", "coordinates": [[[90, 20], [90.01, 20], [90.01, 20.01], [90, 20.01], [90, 20]]]}
    result = river_flood.assess(far_away)  # no tile in the index covers it
    assert result["status"] == "not_modelled"
    assert result["assessed_share_of_parcel"] == 0
    assert result["coverage_note"]


def test_parcel_on_the_tile_edge_is_partial(tiles) -> None:
    polygon = {"type": "Polygon", "coordinates": [[[79.999, 12.5], [80.001, 12.5], [80.001, 12.501], [79.999, 12.501], [79.999, 12.5]]]}
    result = river_flood.assess(polygon)
    assert result["status"] == "partial"
    assert result["assessed_share_of_parcel"] == pytest.approx(0.5, abs=0.02)


def test_provider_failure_is_an_error_and_is_not_cached(tiles, monkeypatch) -> None:
    def broken(*_args, **_kwargs):
        raise rasterio.errors.RasterioIOError("HTTP 503 from provider")

    monkeypatch.setattr(river_flood, "_read", broken)
    with pytest.raises(river_flood.RiverFloodUnavailable, match="503"):
        river_flood.assess(_cells(20, 100, 10, 10))
    assert not (tiles / "flood-hazard" / "results.json").exists()


def test_complete_results_are_reused_from_the_cache(tiles, monkeypatch) -> None:
    first = river_flood.assess(_cells(20, 200, 10, 10))
    assert first["cache"] == "new"

    def must_not_read(*_args, **_kwargs):
        raise AssertionError("a cached parcel was read again")

    monkeypatch.setattr(river_flood, "_read", must_not_read)
    second = river_flood.assess(_cells(20, 200, 10, 10))
    assert second["cache"] == "reused"
    assert second["scenarios"] == first["scenarios"]
