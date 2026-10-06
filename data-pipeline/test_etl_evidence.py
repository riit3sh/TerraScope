"""Guard the honesty of the evidence summaries and the coverage figure."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from connectors.rera_ingest import match_parcel_to_rera
from etl_pipeline import _data_coverage, _elevation_summary, _infrastructure_summary, _rera_summary


SEED = pd.DataFrame([{ "district": "Vellore", "project_name": "P", "rera_registration_number": "TN/1", "promoter_name": "Promoter", "registered_completion_date": "2027-03-31", "source_url": "https://example.invalid" }])


def test_rera_summary_never_claims_this_parcel_is_registered() -> None:
    match = match_parcel_to_rera("Vellore", SEED)
    summary = _rera_summary(match, "Vellore", Path("maharera_seed.csv"), True)
    assert "candidate" in summary.lower()
    assert "stays unknown" in summary
    # The registration belongs to another project; it must be framed as a candidate.
    assert "TN/1" in summary


def test_missing_seed_is_reported_as_unknown_not_as_a_clean_result() -> None:
    match = match_parcel_to_rera("Vellore", pd.DataFrame({"district": pd.Series(dtype="string")}))
    summary = _rera_summary(match, "Vellore", Path("maharera_seed.csv"), False)
    assert "unknown" in summary and "No RERA seed dataset is configured" in summary


def test_absence_from_the_seed_is_not_reported_as_absence_of_registration() -> None:
    match = match_parcel_to_rera("Chennai", SEED)
    summary = _rera_summary(match, "Chennai", Path("maharera_seed.csv"), True)
    assert "partial export" in summary and "stays unknown" in summary


def test_coverage_counts_missing_fields() -> None:
    """The old figure tested always-present dicts and so could never drop below 100."""
    assert _data_coverage({"a": 1, "b": 2}) == 100.0
    assert _data_coverage({"a": 1, "b": None}) == 50.0
    assert _data_coverage({"a": None, "b": None}) == 0.0


def test_infrastructure_summary_carries_the_measured_numbers() -> None:
    summary = _infrastructure_summary({"nearest_road_distance_m": 1240.4, "nearest_road_type": "tertiary", "nearest_school_distance_m": 880})
    assert "1,240 m (tertiary)" in summary and "880 m" in summary
    missing = _infrastructure_summary({})
    assert "no road found" in missing and "no school found" in missing


def test_elevation_summary_reports_unavailable_without_inventing_a_value() -> None:
    summary = _elevation_summary(214.37, {"basis": "12.0 m above baseline.", "baseline_m": 202.37, "relief_m": 48.0, "score": 46})
    assert summary.startswith("Centroid elevation 214.4 m")
    assert "12.0 m above the median of the surrounding terrain" in summary
    assert "/100" not in summary and "46" not in summary  # physical measurements, not the 0-100 figure
    assert _elevation_summary(None, {}).startswith("Elevation unavailable")


if __name__ == "__main__":
    for name, function in sorted(globals().items()):
        if name.startswith("test_"):
            function()
    print("etl evidence checks passed")
