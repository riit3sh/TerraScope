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
