"""Tests for the land valuation import contract, training split and serving."""

from __future__ import annotations

import csv
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from valuation.dataset import AREA_UNITS_IN_SQFT, DatasetError, load_price_csv, property_key
from valuation.fixtures.make_synthetic import build
from valuation.predict import ValuationUnavailable, estimate_value, model_status
from valuation.train import TrainingError, choose_split, train_model


FIXTURE = Path(__file__).parent / "fixtures" / "synthetic_land_prices.csv"


@pytest.fixture(autouse=True)
def _allow_synthetic_model(monkeypatch: pytest.MonkeyPatch) -> None:
    """These tests exercise model mechanics on the synthetic fixture on purpose."""
    monkeypatch.setenv("VALUATION_ALLOW_SYNTHETIC", "true")
COLUMNS = [
    "record_id", "latitude", "longitude", "district", "state", "area_value", "area_unit",
    "land_use", "observation_date", "price_value", "price_unit", "price_basis", "source",
]


def _write(rows: list[dict[str, object]], path: Path) -> Path:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
    return path


def _row(**overrides: object) -> dict[str, object]:
    base = {
        "record_id": "R1", "latitude": 18.52, "longitude": 73.85, "district": "Pune",
        "state": "Maharashtra", "area_value": 1000, "area_unit": "sqft", "land_use": "residential",
        "observation_date": "2023-05-01", "price_value": 5_000_000, "price_unit": "total_inr",
        "price_basis": "transaction", "source": "TEST",
    }
    base.update(overrides)
    return base


# --- import contract -------------------------------------------------------

def test_missing_columns_are_refused_with_the_contract_named(tmp_path: Path) -> None:
    path = tmp_path / "bad.csv"
    path.write_text("latitude,longitude\n1,2\n", encoding="utf-8")
    with pytest.raises(DatasetError, match="missing required columns"):
        load_price_csv(path)


def test_units_are_normalized_to_price_per_sqft(tmp_path: Path) -> None:
    """One plot priced five ways must normalize to the same INR/sqft."""
    rows = [
        _row(record_id="A", price_value=5000, price_unit="inr_per_sqft"),
        _row(record_id="B", price_value=5_000_000, price_unit="total_inr"),
        _row(record_id="C", price_value=5000 * AREA_UNITS_IN_SQFT["sqm"], price_unit="inr_per_sqm"),
        _row(record_id="D", price_value=5000 * AREA_UNITS_IN_SQFT["acre"], price_unit="inr_per_acre"),
        _row(record_id="E", price_value=5000 * AREA_UNITS_IN_SQFT["cent"], price_unit="inr_per_cent"),
    ]
    # Nudge coordinates so these count as five distinct properties, not re-listings.
    for index, row in enumerate(rows):
        row["latitude"] = 18.52 + index * 0.01
    frame, _ = load_price_csv(_write(rows, tmp_path / "units.csv"))
    assert len(frame) == 5
    assert frame["price_inr_per_sqft"].round(4).nunique() == 1
    assert frame["price_inr_per_sqft"].iloc[0] == pytest.approx(5000.0, rel=1e-6)


def test_area_units_convert(tmp_path: Path) -> None:
    rows = [
        _row(record_id="A", area_value=1, area_unit="acre", price_value=100, price_unit="inr_per_sqft"),
        _row(record_id="B", area_value=1, area_unit="hectare", price_value=100, price_unit="inr_per_sqft", latitude=18.6),
    ]
    frame, _ = load_price_csv(_write(rows, tmp_path / "areas.csv"))
    by_id = frame.set_index("record_id")["area_sqft"]
    assert by_id["A"] == pytest.approx(43560.0)
    assert by_id["B"] == pytest.approx(107639.104, rel=1e-6)


def test_invalid_rows_are_dropped_and_counted(tmp_path: Path) -> None:
    rows = [
        _row(record_id="good", latitude=18.52),
        _row(record_id="bad_area", area_value=0, latitude=18.53),
        _row(record_id="bad_unit", area_unit="bigha", latitude=18.54),
        _row(record_id="bad_use", land_use="spaceport", latitude=18.55),
        _row(record_id="bad_date", observation_date="not-a-date", latitude=18.56),
        _row(record_id="bad_basis", price_basis="rumour", latitude=18.57),
    ]
    frame, report = load_price_csv(_write(rows, tmp_path / "mixed.csv"))
    assert frame["record_id"].tolist() == ["good"]
    assert report.rows_read == 6 and report.rows_kept == 1
    assert set(report.dropped) == {
        "non_positive_area", "unsupported_area_unit", "unsupported_land_use",
        "unparseable_observation_date", "unsupported_price_basis",
    }


def test_bigha_is_refused_rather_than_guessed(tmp_path: Path) -> None:
    """Bigha has no national size; silently converting it would corrupt areas."""
    assert "bigha" not in AREA_UNITS_IN_SQFT
    rows = [_row(record_id=str(i), area_unit="bigha", latitude=18.5 + i / 100) for i in range(3)]
    with pytest.raises(DatasetError, match="import contract"):
        load_price_csv(_write(rows, tmp_path / "bigha.csv"))


def test_relisted_property_collapses_to_one_row(tmp_path: Path) -> None:
    """The same plot advertised three times must not become three samples."""
    rows = [
        _row(record_id="listing1", observation_date="2023-01-01", price_value=5_000_000),
        _row(record_id="listing2", observation_date="2023-06-01", price_value=5_400_000),
        _row(record_id="listing3", observation_date="2024-01-01", price_value=5_900_000),
    ]
    frame, report = load_price_csv(_write(rows, tmp_path / "relist.csv"))
    assert len(frame) == 1, "re-listings of one plot must collapse"
    assert report.duplicate_properties_collapsed == 2
    assert frame["record_id"].iloc[0] == "listing3", "the most recent observation should win"


def test_property_key_is_stable_under_tiny_coordinate_noise() -> None:
    a = pd.Series({"latitude": 18.520001, "longitude": 73.850001, "area_sqft": 1000.0, "land_use": "residential"})
    b = pd.Series({"latitude": 18.520002, "longitude": 73.850002, "area_sqft": 1002.0, "land_use": "residential"})
    far = pd.Series({"latitude": 18.9, "longitude": 73.850001, "area_sqft": 1000.0, "land_use": "residential"})
    assert property_key(a) == property_key(b)
    assert property_key(a) != property_key(far)


# --- training and validation ----------------------------------------------

def test_a_thin_dataset_is_refused_rather_than_scored(tmp_path: Path) -> None:
    """Too little data must raise, never yield an unvalidated accuracy claim."""
    rows = [_row(record_id=str(i), latitude=18.5 + i / 100) for i in range(12)]
    with pytest.raises(TrainingError):
        train_model(_write(rows, tmp_path / "thin.csv"), tmp_path / "model.joblib")


def test_single_month_dataset_falls_back_to_geographic_holdout() -> None:
    """Without a time span, districts are held out instead."""
    rows = []
    for district_index, district in enumerate(["Pune", "Nashik", "Thane", "Nagpur", "Vellore"]):
        for row_index in range(20):
            rows.append({
                "latitude": 18.0 + district_index, "longitude": 73.0 + district_index,
                "district": district, "area_sqft": 1000.0 + row_index,
                "observation_date": pd.Timestamp("2024-03-05"),
                "price_inr_per_sqft": 1000.0 + district_index * 500,
                "property_key": f"{district}-{row_index}",
            })
    frame = pd.DataFrame(rows)
    _, _, strategy, label = choose_split(frame)
    assert strategy == "geographic" and "held out entirely" in label


def test_training_reports_measured_holdout_metrics_and_a_baseline(tmp_path: Path) -> None:
    metadata = train_model(FIXTURE, tmp_path / "model.joblib", is_synthetic=True)
    validation = metadata["validation"]
    assert validation["strategy"] in {"temporal", "geographic"}
    assert validation["holdout_rows"] >= 10
    for block in ("model", "baseline"):
        assert validation[block]["mae_inr_per_sqft"] > 0
        assert validation[block]["rmse_inr_per_sqft"] >= validation[block]["mae_inr_per_sqft"]
    assert metadata["is_synthetic"] is True
    assert (tmp_path / "model.metadata.json").exists()


def test_a_range_is_only_offered_when_it_holds_up_out_of_sample(tmp_path: Path) -> None:
    metadata = train_model(FIXTURE, tmp_path / "model.joblib", is_synthetic=True)
    interval = metadata["validation"]["interval"]
    measured, nominal = interval["measured_holdout_coverage_pct"], interval["nominal_coverage_pct"]
    assert interval["reportable"] is (measured >= 0.75 * nominal)
    result = estimate_value(18.52, 73.85, 2000, model_path=tmp_path / "model.joblib")
    if interval["reportable"]:
        assert result["range"]["low_inr_per_sqft"] <= result["estimated_inr_per_sqft"] <= result["range"]["high_inr_per_sqft"]
    else:
        assert result["range"] is None and "only" in result["range_unavailable_reason"]


# --- serving ---------------------------------------------------------------

def test_covered_location_returns_a_priced_estimate() -> None:
    result = estimate_value(18.52, 73.85, 2400, "residential", valuation_date=date(2026, 1, 15))
    assert result["status"] == "available"
    assert result["estimated_inr_per_sqft"] > 0
    assert result["estimated_total_inr"] == pytest.approx(result["estimated_inr_per_sqft"] * 2400, rel=1e-6)
    assert result["valuation_date"] == "2026-01-15"
    assert result["model_version"] and result["data_version"]
    assert result["evidence_coverage"]["observations_within_radius"] >= 5


def test_uncovered_location_is_refused_explicitly() -> None:
    """A parcel far from any observation must get a refusal, not a guess."""
    with pytest.raises(ValuationUnavailable) as caught:
        # Mid-Indian-Ocean: nowhere near any row in any fixture.
        estimate_value(-15.0, 75.0, 2000)
    assert caught.value.reason == "location_not_covered"
    assert "km of this parcel" in caught.value.detail


def test_unknown_land_use_is_refused() -> None:
    with pytest.raises(ValuationUnavailable) as caught:
        estimate_value(18.52, 73.85, 2000, land_use="spaceport")
    assert caught.value.reason == "unsupported_land_use"


def test_bad_area_is_refused() -> None:
    with pytest.raises(ValuationUnavailable) as caught:
        estimate_value(18.52, 73.85, 0)
    assert caught.value.reason == "invalid_input"


def test_missing_model_reports_unavailable_rather_than_crashing(tmp_path: Path) -> None:
    status = model_status(tmp_path / "absent.joblib")
    assert status["available"] is False and status["reason"] == "model_not_trained"


def test_synthetic_artifacts_stay_flagged_as_synthetic() -> None:
    """Demo data must never be presentable as real market evidence."""
    assert model_status()["is_synthetic"] is True
    assert estimate_value(18.52, 73.85, 2000)["is_synthetic"] is True


def test_total_scales_linearly_with_area() -> None:
    small = estimate_value(18.52, 73.85, 1000)
    large = estimate_value(18.52, 73.85, 1000)
    assert small["estimated_inr_per_sqft"] == large["estimated_inr_per_sqft"]


def test_fixture_rows_are_labelled_synthetic() -> None:
    assert all(row["source"] == "SYNTHETIC_FIXTURE" for row in build(rows_per_district=2))


def test_synthetic_model_prices_nothing_unless_demo_mode_is_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    """A price learned from invented rows is an invented price; refuse it by default."""
    monkeypatch.delenv("VALUATION_ALLOW_SYNTHETIC")
    with pytest.raises(ValuationUnavailable) as refused:
        estimate_value(18.52, 73.85, 2000)
    assert refused.value.reason == "synthetic_model_only"
    # The refusal text is shown in the report, so it must stay free of operator
    # instructions; those belong in docs/SETUP_VALUATION.md.
    detail = refused.value.detail
    for leak in ("VALUATION_ALLOW_SYNTHETIC", "python -m valuation.train", "README.md", "--synthetic"):
        assert leak not in detail, f"operator instruction {leak!r} leaked into the user-facing report"
    assert "no price is quoted" in detail
