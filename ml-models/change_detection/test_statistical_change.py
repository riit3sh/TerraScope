from change_detection.statistical_change import STABLE_LIMIT, detect_change_from_series, seasonal_pairs

# Quarterly dates over two years: each first-year date has a partner 365 days later.
DATES = ["2024-11-26", "2025-02-25", "2025-05-27", "2025-08-26", "2025-11-26", "2026-02-25", "2026-05-27", "2026-08-26"]
SEASONAL_NDVI = [0.55, 0.40, 0.25, 0.45]  # strong monsoon / dry-season swing, the same each year


def series(year2_ndvi_shift=0.0, year2_ndbi_shift=0.0, noise=(0, 0, 0, 0)):
    rows = []
    for index, day in enumerate(DATES):
        season, second = index % 4, index >= 4
        rows.append({"date": day,
                     "ndvi": SEASONAL_NDVI[season] + (year2_ndvi_shift + noise[season] if second else 0.0),
                     "ndbi": -0.10 + (year2_ndbi_shift if second else 0.0)})
    return rows


def test_pairs_are_same_season_a_year_apart() -> None:
    pairs = seasonal_pairs(series())
    assert [(a["date"], b["date"]) for a, b in pairs] == list(zip(DATES[:4], DATES[4:]))


def test_seasonal_swing_alone_is_no_change() -> None:
    """Regression: v1 fitted one line through monsoon and summer and called it 'no change, 12% confidence'."""
    result = detect_change_from_series(series())
    assert result["change_type"] == "no_change" and result["change_detected"] is False
    assert result["change_confidence"] is None  # no uncalibrated percentage
    assert result["change_method"]["pairs"] == 4 and result["change_method"]["calibrated"] is False


def test_consistent_loss_of_green_and_rise_in_built_up_is_construction() -> None:
    result = detect_change_from_series(series(year2_ndvi_shift=-0.2, year2_ndbi_shift=0.15))
    assert result["change_type"] == "construction_growth" and result["change_detected"] is True


def test_vegetation_loss_and_gain() -> None:
    assert detect_change_from_series(series(year2_ndvi_shift=-0.2))["change_type"] == "vegetation_loss"
    assert detect_change_from_series(series(year2_ndvi_shift=0.2))["change_type"] == "vegetation_gain"


def test_pairs_that_disagree_are_inconclusive_not_no_change() -> None:
    result = detect_change_from_series(series(noise=(0.12, -0.10, 0.02, 0.0)))
    assert result["change_type"] == "inconclusive" and result["change_detected"] is None
    assert "does not support" in result["change_method"]["reason"]


def test_small_noise_stays_no_change() -> None:
    almost = STABLE_LIMIT * 0.8
    assert detect_change_from_series(series(noise=(almost, -almost, almost, 0)))["change_type"] == "no_change"


def test_too_few_seasonal_pairs_is_inconclusive() -> None:
    """Eight dates inside one season cannot separate change from seasonal variation."""
    rows = [{"date": f"2024-03-{day:02d}", "ndvi": 0.5, "ndbi": 0.1} for day in range(1, 9)]
    result = detect_change_from_series(rows)
    assert result["change_type"] == "inconclusive" and "same-season pair" in result["change_method"]["reason"]


def test_fewer_than_two_observations_is_insufficient_evidence() -> None:
    assert detect_change_from_series([{"date": "2025-01-01", "ndvi": 0.3, "ndbi": 0.0}])["change_type"] == "insufficient_evidence"
