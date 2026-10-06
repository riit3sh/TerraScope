"""Surface-water statistics and height above mapped water, on synthetic rasters."""

from __future__ import annotations

import numpy as np
import rasterio
from rasterio.transform import from_origin
from shapely.geometry import LineString

from connectors import flood_indicators
from connectors.local_osm import LocalOSM, create_store, write_features

RES = 0.00025  # JRC GSW pixel size (degrees)
WEST, NORTH = 79.0, 13.0


def _tif(path, array, res=RES, dtype="uint8"):
    path.parent.mkdir(parents=True, exist_ok=True)
    with rasterio.open(path, "w", driver="GTiff", width=array.shape[1], height=array.shape[0], count=1,
                       dtype=dtype, crs="EPSG:4326", transform=from_origin(WEST, NORTH, res, res)) as dst:
        dst.write(array.astype(dtype), 1)


def _parcel(col0, row0, cols, rows, res=RES):
    lon0, lat0 = WEST + col0 * res, NORTH - row0 * res
    lon1, lat1 = lon0 + cols * res, lat0 - rows * res
    return {"type": "Polygon", "coordinates": [[[lon0, lat1], [lon1, lat1], [lon1, lat0], [lon0, lat0], [lon0, lat1]]]}


def test_surface_water_separates_parcel_from_surroundings(tmp_path) -> None:
    occurrence = np.zeros((400, 400))
    occurrence[100:110, 100:110] = 80          # water seen 80% of the time, inside the parcel
    occurrence[100:110, 140:150] = 30          # a pond ~800 m east: inside the 500 m buffer only partly
    occurrence[0:5, :] = 255                   # no-observation pixels must be ignored
    extent = (occurrence > 0) & (occurrence <= 100)
    _tif(tmp_path / "gsw" / "occurrence_test.tif", occurrence)
    _tif(tmp_path / "gsw" / "extent_test.tif", extent)

    result = flood_indicators.surface_water(_parcel(100, 100, 20, 20), tmp_path)
    inside, around = result["parcel"], result["within_buffer"]
    assert inside["occurrence_max_pct"] == 80
    assert 0.2 < inside["water_ever_fraction"] < 0.35  # 100 of ~400 touched pixels
    assert around["pixels"] > inside["pixels"]
    assert around["occurrence_max_pct"] == 80
    assert result["buffer_m"] == 500


def test_dry_parcel_reports_zero_not_missing(tmp_path) -> None:
    _tif(tmp_path / "gsw" / "occurrence_test.tif", np.zeros((200, 200)))
    _tif(tmp_path / "gsw" / "extent_test.tif", np.zeros((200, 200)))
    result = flood_indicators.surface_water(_parcel(50, 50, 10, 10), tmp_path)
    assert result["parcel"]["occurrence_max_pct"] == 0
    assert result["parcel"]["water_ever_fraction"] == 0.0


def test_height_above_nearest_mapped_water(tmp_path, monkeypatch) -> None:
    dem_res = 1 / 3600
    dem = np.full((3600, 3600), 20.0)
    dem[1000:1003, :] = 12.0  # a channel along one row of pixels
    # Tile name follows the Copernicus pattern for the 1x1 degree cell N12 E079.
    _tif(tmp_path / "dem" / "Copernicus_DSM_COG_10_N12_00_E079_00_DEM.tif", dem, res=dem_res, dtype="float32")
    channel_lat = NORTH - 1001.5 * dem_res

    store = tmp_path / "osm.sqlite"
    connection = create_store(store)
    write_features(connection, [("waterway", "canal", "Test Canal", "w1", {}, LineString([(79.1, channel_lat), (79.2, channel_lat)]))])
    connection.commit()
    connection.close()

    parcel = _parcel(540, 980, 10, 10, res=dem_res)  # ~20 px north of the channel
    osm = LocalOSM(store)
    try:
        result = flood_indicators.terrain_above_water(parcel, osm, tmp_path)
    finally:
        osm.close()
    assert result["parcel_elevation_m"] == 20.0
    assert result["nearest_water_feature_class"] == "canal"
    assert result["water_feature_elevation_m"] == 12.0
    assert result["elevation_above_nearest_water_m"] == 8.0
