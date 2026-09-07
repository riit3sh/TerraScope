from change_detection.statistical_change import detect_change_from_series


def test_construction_growth_has_high_confidence() -> None:
    series = [
        {"date": f"2024-01-{day:02d}", "ndvi": 0.70 - 0.01 * day, "ndbi": 0.10 + 0.01 * day}
        for day in range(1, 8)
    ]
    result = detect_change_from_series(series)
    assert result["change_detected"] is True
    assert result["change_type"] == "construction_growth"
    assert result["change_confidence"] >= 0.8


def test_flat_series_is_no_change() -> None:
    series = [
        {"date": f"2024-02-{day:02d}", "ndvi": 0.45, "ndbi": 0.12}
        for day in range(1, 8)
    ]
    result = detect_change_from_series(series)
    assert result["change_detected"] is False
    assert result["change_type"] == "no_change"
    assert result["change_confidence"] <= 0.1


def test_noisy_flat_series_does_not_false_positive() -> None:
    ndvi_noise = [0.004, -0.006, 0.003, -0.002, 0.005, -0.004, 0.001, -0.003]
    ndbi_noise = [-0.003, 0.004, -0.002, 0.003, -0.004, 0.002, -0.001, 0.003]
    series = [
        {"date": f"2024-03-{day:02d}", "ndvi": 0.50 + ndvi_noise[day - 1], "ndbi": 0.15 + ndbi_noise[day - 1]}
        for day in range(1, 9)
    ]
    result = detect_change_from_series(series)
    assert result["change_detected"] is False
    assert result["change_type"] == "no_change"
