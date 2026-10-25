"""The per-year shares and trends, from synthetic class histograms (no network)."""

import numpy as np

from connectors.land_cover_history import CLOUDS, summarise


def histogram(**counts: int) -> np.ndarray:
    codes = {"built": 7, "crops": 5, "water": 1, "clouds": CLOUDS, "nodata": 0}
    out = np.zeros(256, dtype=np.int64)
    for name, value in counts.items():
        out[codes[name]] = value
    return out


def year(built_near: int, plot: str = "crops") -> dict:
    return {"parcel": histogram(**{plot: 10}),
            "near": histogram(built=built_near, crops=100 - built_near),
            "far": histogram(built=20, crops=80)}


EXPECTED = {"parcel": 10, "near": 100, "far": 100}


def test_trend_is_the_least_squares_slope_in_points_per_year() -> None:
    result = summarise({2017 + i: year(10 + 2 * i) for i in range(7)}, EXPECTED)
    assert result["status"] == "assessed"
    trend = result["trend_within_1km"]
    assert (trend["first_share"], trend["last_share"], trend["slope_pts_per_year"]) == (0.1, 0.22, 2.0)
    assert result["trend_1_to_3km"]["slope_pts_per_year"] == 0.0
    assert [p["dominant"] for p in result["parcel"]] == ["crops"] * 7


def test_a_mostly_clouded_year_is_dropped_not_read_from_a_sliver() -> None:
    counts = {2017 + i: year(10 + 2 * i) for i in range(7)}
    counts[2020] = {**year(0), "near": histogram(built=9, crops=1, clouds=90)}  # 10% of the ring classified
    result = summarise(counts, EXPECTED)
    assert result["trend_within_1km"]["years_used"] == 6
    assert next(r for r in result["surroundings"] if r["year"] == 2020)["built_share_within_1km"] is None


def test_too_few_years_give_no_trend() -> None:
    result = summarise({2022: year(10), 2023: year(12)}, EXPECTED)
    assert result["status"] == "insufficient" and result["trend_within_1km"] is None


def test_a_flat_series_is_stored_as_zero_not_negative_zero() -> None:
    """The Vijayawada series: a dip in 2020-2022 makes the fit ~-3e-15, which rounded to -0.0."""
    import math
    near = [0.8822, 0.8817, 0.8822, 0.8803, 0.8782, 0.8783, 0.8858]
    counts = {2017 + i: {"parcel": histogram(built=10), "near": histogram(built=round(v * 10000), crops=10000 - round(v * 10000)),
                         "far": histogram(built=20, crops=80)} for i, v in enumerate(near)}
    slope = summarise(counts, {"parcel": 10, "near": 10000, "far": 100})["trend_within_1km"]["slope_pts_per_year"]
    assert slope == 0.0 and math.copysign(1.0, slope) == 1.0


def test_cached_results_are_reused_and_invalidated_by_geometry_or_dataset_version(tmp_path, monkeypatch) -> None:
    from connectors import flood_indicators, land_cover_history as lc
    monkeypatch.setattr(flood_indicators, "_result_cache_path", lambda: tmp_path / "cache.json")
    reads = []

    def fake_tiles(item, polygon, token):
        reads.append(item["id"])
        year = 2017 + int(item["id"])
        return year, {"parcel": histogram(built=10), "near": histogram(built=40, crops=60), "far": histogram(built=20, crops=80)}

    monkeypatch.setattr(lc, "_search", lambda polygon: [{"id": str(i)} for i in range(7)])
    monkeypatch.setattr(lc, "_sas_token", lambda: "t")
    monkeypatch.setattr(lc, "_tile_counts", fake_tiles)
    monkeypatch.setattr(lc, "_expected_pixels", lambda polygon: {"parcel": 10, "near": 100, "far": 100})
    square = {"type": "Polygon", "coordinates": [[[79.0, 12.0], [79.001, 12.0], [79.001, 12.001], [79.0, 12.001], [79.0, 12.0]]]}
    assert lc.assess(square)["cache"] == "new" and len(reads) == 7
    assert lc.assess(square)["cache"] == "reused" and len(reads) == 7, "same plot, same dataset: no re-read"
    moved = {"type": "Polygon", "coordinates": [[[x + 0.0001, y] for x, y in square["coordinates"][0]]]}
    assert lc.assess(moved)["cache"] == "new" and len(reads) == 14, "a changed boundary is recomputed"
    monkeypatch.setattr(lc, "COLLECTION", "io-lulc-annual-v03")
    assert lc.assess(square)["cache"] == "new" and len(reads) == 21, "a new dataset version is recomputed"


def test_a_failed_read_is_never_cached(tmp_path, monkeypatch) -> None:
    from connectors import flood_indicators, land_cover_history as lc
    monkeypatch.setattr(flood_indicators, "_result_cache_path", lambda: tmp_path / "cache.json")
    monkeypatch.setattr(lc, "_search", lambda polygon: [])
    square = {"type": "Polygon", "coordinates": [[[79.0, 12.0], [79.001, 12.0], [79.001, 12.001], [79.0, 12.0]]]}
    import pytest
    with pytest.raises(RuntimeError):
        lc.assess(square)
    assert not (tmp_path / "cache.json").exists()
