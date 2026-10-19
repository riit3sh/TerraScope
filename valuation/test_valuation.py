"""Land valuation: import contract, cleaning, comparable estimates and honest evaluation.

All rows here are SYNTHETIC test data written in this file. They exercise the
arithmetic and the rules; they say nothing about real land prices.
"""

from __future__ import annotations

from datetime import date, timedelta

import numpy as np
import pandas as pd
import pytest

from valuation import evaluate, predict
from valuation.comparables import ValuationUnavailable, estimate
from valuation.dataset import AREA_UNITS_IN_SQFT, DatasetError, normalize

KATPADI = (12.9600, 79.1400)
TODAY = date(2026, 10, 1)


def row(**overrides) -> dict[str, str]:
    base = {
        "source": "TEST-SOURCE", "source_record_id": "r1", "source_url": "", "reuse_basis": "synthetic test row",
        "price_type": "asking", "observed_date": "2026-09-01", "retrieved_date": "2026-09-02",
        "price_value": "6000000", "price_unit": "total", "currency": "INR",
        "area_value": "2400", "area_unit": "sqft", "property_category": "vacant_plot", "land_use": "residential",
        "latitude": str(KATPADI[0]), "longitude": str(KATPADI[1]), "location_precision": "exact",
        "district": "Vellore", "state": "Tamil Nadu", "locality": "Gandhi Nagar", "attributes": "",
    }
    return {key: str(value) for key, value in {**base, **overrides}.items()}


def frame(*rows: dict[str, str]) -> pd.DataFrame:
    return pd.DataFrame(list(rows))


def plots(n: int, *, price=2500.0, step_m=150.0, area=2400.0, days_ago=30, **extra) -> list[dict[str, str]]:
    """n distinct plots spaced step_m apart east of Katpadi, at price + 10*i ₹/sq ft."""
    out = []
    for i in range(n):
        observed = TODAY - timedelta(days=days_ago + i)
        out.append(row(source_record_id=f"p{i}", longitude=f"{KATPADI[1] + i * step_m / 108_500:.6f}",
                       price_value=f"{(price + 10 * i) * area:.0f}", area_value=f"{area:.0f}",
                       observed_date=observed.isoformat(), retrieved_date=observed.isoformat(), **extra))
    return out


# --- import and cleaning ----------------------------------------------------

@pytest.mark.parametrize("unit, value", [
    ("per_sqft", 2500),
    ("per_sqyd", 22500),           # 9 sq ft per sq yd
    ("per_sqm", 26909.776),        # 10.7639 sq ft per sq m
    ("per_cent", 1_089_000),       # 435.6 sq ft per cent (Tamil Nadu, Kerala)
    ("per_ground", 6_000_000),     # 2,400 sq ft per ground (Chennai)
    ("per_acre", 108_900_000),
])
def test_price_units_convert_to_inr_per_sqft(unit, value):
    cleaned, _ = normalize(frame(row(price_unit=unit, price_value=str(value))))
    assert cleaned["price_inr_per_sqft"].iloc[0] == pytest.approx(2500.0, rel=1e-6)


def test_total_price_uses_the_area_in_its_own_unit():
    cleaned, _ = normalize(frame(row(price_value="5445000", area_value="5", area_unit="cent")))
    assert cleaned["area_sqft"].iloc[0] == pytest.approx(5 * 435.6)
    assert cleaned["price_inr_per_sqft"].iloc[0] == pytest.approx(5445000 / (5 * 435.6))
    assert AREA_UNITS_IN_SQFT["ground"] == 2400.0 and AREA_UNITS_IN_SQFT["guntha"] == 1089.0


@pytest.mark.parametrize("overrides, reason", [
    ({"currency": "USD"}, "currency_not_inr"),
    ({"reuse_basis": ""}, "missing_reuse_basis"),
    ({"price_type": "estimate"}, "unknown_price_type"),
    ({"area_unit": "bigha"}, "invalid_area"),               # varies by state: never converted
    ({"property_category": "apartment"}, "not_vacant_land"),
    ({"property_category": "independent_house"}, "not_vacant_land"),
    ({"property_category": "agricultural_land"}, "category_land_use_mismatch"),
    ({"latitude": "51.5"}, "coordinates_outside_india"),
    ({"price_value": "600"}, "implausible_price_per_sqft"),  # ₹0.25/sq ft: a lakh/crore slip
    ({"area_value": "50", "price_value": "125000"}, "implausible_area"),
    ({"area_value": "", "area_unit": ""}, "total_price_without_area"),
    ({"retrieved_date": "2026-08-01"}, "retrieved_before_observed"),
])
def test_bad_rows_are_dropped_with_a_reason(overrides, reason):
    with pytest.raises(DatasetError, match=reason):
        normalize(frame(row(**overrides)))


def test_missing_columns_are_a_contract_error():
    with pytest.raises(DatasetError, match="Missing required columns"):
        normalize(pd.DataFrame([{"latitude": 1}]))


def test_relistings_of_one_plot_collapse_to_the_latest():
    cleaned, report = normalize(frame(
        row(source="Broker A", source_record_id="a1", price_value="6000000", observed_date="2026-06-01", retrieved_date="2026-06-01"),
        # same plot, another broker, 20 m away, 2% larger area, three months later
        row(source="Broker B", source_record_id="b7", price_value="6300000", area_value="2448",
            latitude=f"{KATPADI[0] + 0.00018:.5f}", observed_date="2026-09-01"),
        # the same record delivered twice
        row(source="Broker B", source_record_id="b7", price_value="6300000", area_value="2448",
            latitude=f"{KATPADI[0] + 0.00018:.5f}", observed_date="2026-09-01", retrieved_date="2026-09-05"),
        # a different plot nearby: twice the size
        row(source="Broker A", source_record_id="a2", area_value="4800", price_value="11000000"),
    ))
    assert report.same_record_repeated == 1
    assert report.duplicate_listings_collapsed == 1
    assert len(cleaned) == 2
    merged = cleaned[cleaned["group_size"] == 2].iloc[0]
    assert merged["source_record_id"] == "b7" and merged["group_sources"] == "Broker A; Broker B"


def test_locality_precision_rows_need_matching_price_to_be_duplicates():
    # Two plots geocoded only to a locality centroid share coordinates; same size is not enough.
    cleaned, report = normalize(frame(
        row(source_record_id="x1", location_precision="locality", price_value="6000000"),
        row(source_record_id="x2", location_precision="locality", price_value="7200000"),
    ))
    assert report.duplicate_listings_collapsed == 0 and len(cleaned) == 2


def test_a_plot_listed_again_a_year_later_is_still_one_property():
    # Regression from the previous contract: three listings of one plot over a year
    # must not become three samples (or straddle a temporal split).
    cleaned, report = normalize(frame(
        row(source_record_id="l1", observed_date="2025-01-01", retrieved_date="2025-01-01", price_value="5000000"),
        row(source_record_id="l2", observed_date="2025-06-01", retrieved_date="2025-06-01", price_value="5400000"),
        row(source_record_id="l3", observed_date="2026-01-01", retrieved_date="2026-01-01", price_value="5900000"),
    ))
    assert len(cleaned) == 1 and report.duplicate_listings_collapsed == 2
    assert cleaned["source_record_id"].iloc[0] == "l3"  # the most recent observation wins


def test_plot_identifiers_merge_and_separate_listings():
    near = f"{KATPADI[0] + 0.0001:.5f}"  # 11 m apart: adjacent layout plots
    cleaned, _ = normalize(frame(
        row(source_record_id="a", property_ref="S.No. 12/3A"),
        row(source_record_id="b", property_ref="S.No. 12/3B", latitude=near),
        # same identifier, coordinates 2 km off (a broker pinned the wrong spot): still one plot
        row(source_record_id="c", property_ref="s.no. 12/3a", latitude=f"{KATPADI[0] + 0.018:.5f}",
            observed_date="2026-09-20", retrieved_date="2026-09-20"),
    ))
    assert sorted(cleaned["source_record_id"]) == ["b", "c"]


def test_area_units_convert_to_square_feet():
    cleaned, _ = normalize(frame(
        row(source_record_id="acre", area_value="1", area_unit="acre", price_unit="per_sqft", price_value="300",
            property_category="agricultural_land", land_use="agricultural"),
        row(source_record_id="ha", area_value="1", area_unit="hectare", price_unit="per_sqft", price_value="300",
            property_category="agricultural_land", land_use="agricultural", latitude="13.5"),
    ))
    areas = cleaned.set_index("source_record_id")["area_sqft"]
    assert areas["acre"] == pytest.approx(43560.0) and areas["ha"] == pytest.approx(107639.104, rel=1e-6)


def test_good_rows_survive_beside_bad_ones_and_every_drop_is_counted():
    cleaned, report = normalize(frame(
        row(source_record_id="good"),
        row(source_record_id="usd", currency="USD", latitude="13.1"),
        row(source_record_id="flat", property_category="apartment", latitude="13.2"),
        row(source_record_id="nodate", observed_date="soon", latitude="13.3"),
        row(source_record_id="bigha", area_unit="bigha", latitude="13.4"),
    ))
    assert cleaned["source_record_id"].tolist() == ["good"]
    assert report.rows_read == 5 and report.rows_kept == 1
    assert report.dropped == {"currency_not_inr": 1, "invalid_area": 1, "not_vacant_land": 1, "unparseable_date": 1}


# --- comparable estimates ---------------------------------------------------

def observations(*rows):
    cleaned, _ = normalize(frame(*rows))
    return cleaned


def ask(data, **overrides):
    args = dict(latitude=KATPADI[0], longitude=KATPADI[1], area_sqft=2400.0, land_use="residential",
                price_type="asking", valuation_date=TODAY)
    return estimate(data, **{**args, **overrides})


def test_estimate_is_the_median_of_nearby_similar_plots():
    result = ask(observations(*plots(7)))
    assert result["estimate_inr_per_sqft"] == pytest.approx(2530.0)        # median of 2500..2560
    assert result["comparable_count"] == 7 and result["radius_km"] == 1.0
    assert result["spread_inr_per_sqft"]["p25"] == pytest.approx(2515.0)
    assert result["total_inr"]["estimate"] == pytest.approx(2530.0 * 2400)
    assert "not a statistically validated prediction interval" in result["spread_basis"]
    assert any("Asking prices" in reason for reason in result["uncertainty"])
    assert result["comparables"][0]["source_record_id"] == "p0"           # nearest first, with provenance


def test_asking_and_transaction_prices_are_never_pooled():
    with pytest.raises(ValuationUnavailable) as refusal:
        ask(observations(*plots(7)), price_type="transaction")
    assert refusal.value.reason == "price_type_not_covered"


def test_agricultural_land_is_not_valued_from_residential_plots():
    with pytest.raises(ValuationUnavailable) as refusal:
        ask(observations(*plots(7)), land_use="agricultural", area_sqft=43560.0)
    assert refusal.value.reason == "land_use_not_covered"


def test_a_campus_is_not_valued_from_house_plots():
    with pytest.raises(ValuationUnavailable) as refusal:
        ask(observations(*plots(7)), area_sqft=150 * 43560.0)  # ~150 acres
    assert refusal.value.reason == "area_outside_support"
    assert "2,400-2,400 sq ft" in refusal.value.detail


def test_too_few_comparables_is_a_refusal_not_a_guess():
    with pytest.raises(ValuationUnavailable) as refusal:
        ask(observations(*plots(4)))
    assert refusal.value.reason == "insufficient_comparables"


def test_far_away_data_is_not_used():
    with pytest.raises(ValuationUnavailable) as refusal:
        ask(observations(*plots(7)), latitude=14.47, longitude=78.82)  # Kadapa, ~190 km away
    assert refusal.value.reason == "no_comparables_nearby"
    assert "nearest:" in refusal.value.detail and "km" in refusal.value.detail


@pytest.mark.parametrize("overrides", [{"land_use": "spaceport"}, {"price_type": "rumour"}])
def test_unknown_categories_are_invalid_input(overrides):
    with pytest.raises(ValuationUnavailable) as refusal:
        ask(observations(*plots(7)), **overrides)
    assert refusal.value.reason == "invalid_input"  # the route answers 400


def test_total_scales_with_area_but_the_rate_does_not():
    sizes = [2000, 2200, 2400, 2600, 2800, 3000, 3200]
    rows = [dict(r, area_value=str(a), price_value=str(2500 * a)) for r, a in zip(plots(7), sizes)]
    data = observations(*rows)
    small, large = ask(data, area_sqft=2400.0), ask(data, area_sqft=3000.0)
    assert small["estimate_inr_per_sqft"] == large["estimate_inr_per_sqft"] == 2500.0
    assert large["total_inr"]["estimate"] == pytest.approx(small["total_inr"]["estimate"] * 3000 / 2400)
    # Inside the 1/3x-3x similarity band but beyond the largest comparable: no total.
    beyond = ask(data, area_sqft=5000.0)
    assert beyond["total_inr"] is None and any("size range" in r for r in beyond["uncertainty"])


def test_stale_listings_are_excluded():
    with pytest.raises(ValuationUnavailable) as refusal:
        ask(observations(*plots(7, days_ago=700)))
    assert refusal.value.reason == "stale_data_only"


def test_the_radius_grows_only_as_far_as_needed():
    result = ask(observations(*plots(6, step_m=600)))  # 0, 0.6, ... 3.0 km
    assert result["radius_km"] == 5.0 and result["comparable_count"] == 6
    assert any("up to 5 km" in reason for reason in result["uncertainty"])


def test_future_observations_are_ignored():
    with pytest.raises(ValuationUnavailable):
        ask(observations(*plots(7)), valuation_date=TODAY - timedelta(days=90))


def test_locality_level_and_coarser_locations():
    coarse = [dict(r, location_precision="pincode") for r in plots(7)]
    with pytest.raises(ValuationUnavailable) as refusal:
        ask(observations(*coarse))
    assert refusal.value.reason == "no_comparables_nearby"
    locality = [dict(r, location_precision="locality") for r in plots(7)]
    assert any("only to a locality" in reason for reason in ask(observations(*locality))["uncertainty"])


# --- serving ----------------------------------------------------------------

def test_no_data_file_means_an_explicit_refusal(tmp_path, monkeypatch):
    monkeypatch.setenv("VALUATION_OBSERVATIONS_PATH", str(tmp_path / "missing.csv"))
    with pytest.raises(ValuationUnavailable) as refusal:
        predict.estimate_value(KATPADI[0], KATPADI[1], 2400.0)
    assert refusal.value.reason == "no_price_data"
    assert predict.data_status()["available"] is False
    # Shown in the report: it explains, but carries no operator instructions.
    for leak in ("VALUATION_", "python -m", "README", ".csv", "data-cache"):
        assert leak not in refusal.value.detail


@pytest.mark.parametrize("args", [(0, "residential", "asking"), (2400, "spaceport", "asking"), (2400, "residential", "rumour")])
def test_bad_requests_are_invalid_input_even_with_no_data(tmp_path, monkeypatch, args):
    monkeypatch.setenv("VALUATION_OBSERVATIONS_PATH", str(tmp_path / "missing.csv"))
    with pytest.raises(ValuationUnavailable) as refusal:
        predict.estimate_value(KATPADI[0], KATPADI[1], *args)
    assert refusal.value.reason == "invalid_input"


def test_served_estimate_carries_data_version_and_validation_status(tmp_path, monkeypatch):
    path = tmp_path / "observations.csv"
    frame(*plots(7)).to_csv(path, index=False)
    monkeypatch.setenv("VALUATION_OBSERVATIONS_PATH", str(path))
    result = predict.estimate_value(KATPADI[0], KATPADI[1], 2400.0, valuation_date=TODAY)
    assert result["status"] == "available" and result["data_version"]
    assert result["validation"]["status"] == "not_yet_validated"


# --- evaluation ---------------------------------------------------------------

def market(n_plots: int, seed: int = 3) -> pd.DataFrame:
    """Synthetic market: 4 towns, prices rising 1%/month, ±10% noise, some re-listings."""
    rng = np.random.default_rng(seed)
    towns = [(12.96, 79.14, "Vellore"), (13.08, 80.27, "Chennai"), (14.47, 78.82, "Kadapa"), (11.93, 79.83, "Puducherry")]
    rows = []
    for i in range(n_plots):
        lat, lon, district = towns[i % 4]
        lat, lon = lat + rng.uniform(-0.02, 0.02), lon + rng.uniform(-0.02, 0.02)
        months = int(rng.integers(0, 24))
        observed = date(2024, 10, 1) + timedelta(days=30 * months)
        price = 3000 * (1.01 ** months) * rng.uniform(0.9, 1.1)
        area = float(rng.uniform(1200, 4800))
        base = row(source_record_id=f"m{i}", latitude=f"{lat:.5f}", longitude=f"{lon:.5f}", district=district,
                   area_value=f"{area:.0f}", price_value=f"{price * area:.0f}",
                   observed_date=observed.isoformat(), retrieved_date=observed.isoformat())
        rows.append(base)
        if i % 10 == 0:  # the same plot re-listed by another broker
            rows.append(dict(base, source="TEST-BROKER-2", price_value=f"{price * area * 1.02:.0f}"))
    cleaned, _ = normalize(frame(*rows))
    return cleaned


def test_metric_arithmetic():
    result = evaluate.metrics(np.array([100.0, 200.0, 400.0]), np.array([110.0, 150.0, 400.0]))
    assert result["mae_inr_per_sqft"] == pytest.approx(20.0)
    assert result["rmse_inr_per_sqft"] == pytest.approx(np.sqrt((100 + 2500) / 3), abs=0.01)
    assert result["median_ape_pct"] == pytest.approx(10.0)
    assert (result["within_10_pct"], result["within_20_pct"], result["within_30_pct"]) == (66.7, 66.7, 100.0)


def test_evaluation_splits_never_share_a_property_and_report_both_holdouts():
    data = market(600)
    assert data["group_id"].is_unique  # re-listings collapsed before any split
    report = evaluate.evaluate(data, "asking")
    assert set(report["holdouts"]) == {"temporal", "geographic"}
    temporal = report["holdouts"]["temporal"]
    assert temporal["train_dates"][1] <= temporal["test_dates"][0]
    assert temporal["status"] == "validated" and temporal["baseline"]["mae_inr_per_sqft"] > 0
    assert temporal["estimates"] + sum(temporal["refusals"].values()) == temporal["test_observations"]
    assert "not a calibrated interval" in temporal["baseline_spread"]["note"]
    assert "beats_baseline_on_mae" in temporal["model"]  # 600 rows: the model is compared
    # Whole towns held out: no comparables within 10 km, so the baseline refuses instead of guessing.
    geographic = report["holdouts"]["geographic"]
    assert geographic["estimates"] == 0 and geographic["refusals"] == {"no_comparables_nearby": geographic["test_observations"]}
    assert report["status"] == "not_yet_validated"


def test_a_single_month_of_data_gets_only_a_geographic_holdout():
    data = market(400)
    data["observed_date"] = pd.Timestamp("2026-03-05")
    assert [name for name, *_ in evaluate.splits(data)] == ["geographic"]


def test_small_datasets_are_not_yet_validated_and_quote_no_errors():
    report = evaluate.evaluate(market(60), "asking")
    for holdout in report["holdouts"].values():
        assert holdout["status"] == "not_yet_validated" and holdout["baseline"] is None
    assert report["status"] == "not_yet_validated"


# --- import workflow: preview, then commit -----------------------------------------

def test_preview_explains_every_row_and_writes_nothing(tmp_path):
    from valuation import importer

    rows = plots(6, days_ago=40) + [
        row(source_record_id="bad-currency", currency="USD"),
        row(source_record_id="no-permission", reuse_basis=""),
        row(source_record_id="old", observed_date="2024-01-10", retrieved_date="2024-01-11", longitude="79.2000"),
        row(source_record_id="town", location_precision="pincode", longitude="79.2500"),
        plots(1, days_ago=40)[0],  # the same record delivered twice
    ]
    result = importer.preview(frame(*rows), today=TODAY)
    assert result["ok"] and result["rows_read"] == 11
    assert {(r["row"], r["reason"]) for r in result["rejected"]} == {(8, "currency_not_inr"), (9, "missing_reuse_basis")}
    assert result["duplicates"] == [{"row": 2, "kind": "same_record_repeated", "kept_row": 12}]
    assert result["stale_rows"] == [10]
    assert result["coarse_location_rows"] == [11]
    assert result["usable_as_comparables_today"] == 6
    assert [g["price_type"] for g in result["groups"]] == ["asking"]
    assert not list(tmp_path.iterdir())


def test_preview_keeps_price_bases_and_land_uses_apart():
    from valuation import importer

    rows = plots(3, days_ago=20) + [
        row(source_record_id="g1", price_type="guideline", price_value="1800", price_unit="per_sqft", area_value="", area_unit=""),
        row(source_record_id="c1", land_use="commercial", longitude="79.1600"),
    ]
    groups = {(g["price_type"], g["land_use"]): g["rows"] for g in importer.preview(frame(*rows), today=TODAY)["groups"]}
    assert groups == {("asking", "residential"): 3, ("guideline", "residential"): 1, ("asking", "commercial"): 1}


def test_commit_appends_valid_rows_backs_up_and_serves_them(tmp_path, monkeypatch):
    from valuation import importer

    path = tmp_path / "observations.csv"
    first = importer.commit(frame(*plots(5, days_ago=20)), path, today=TODAY)
    assert first["rows_added"] == 5 and first["backup"] is None
    second = importer.commit(frame(*plots(3, days_ago=25, step_m=900.0), row(source_record_id="x", currency="USD")),
                             path, today=TODAY)
    assert second["rows_added"] == 3 and second["rows_rejected"] == 1 and second["rows_in_file"] == 8
    assert (tmp_path / second["backup"]).exists()
    monkeypatch.setenv("VALUATION_OBSERVATIONS_PATH", str(path))
    served = predict.estimate_value(KATPADI[0], KATPADI[1], 2400, valuation_date=TODAY)
    assert served["status"] == "available" and served["comparable_count"] >= 5


def test_commit_refuses_a_file_with_no_valid_rows(tmp_path):
    from valuation import importer

    with pytest.raises(DatasetError):
        importer.commit(frame(row(currency="USD")), tmp_path / "observations.csv", today=TODAY)
    assert not (tmp_path / "observations.csv").exists()
