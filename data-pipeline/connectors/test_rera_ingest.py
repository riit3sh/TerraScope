"""Guard the RERA fields that cross into the evidence snapshot."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from connectors.rera_ingest import RERA_SNAPSHOT_FIELDS, match_parcel_to_rera


SCHEMA = json.loads((Path(__file__).resolve().parents[2] / "docs" / "schema" / "parcel_schema.json").read_text(encoding="utf-8"))
ALLOWED = set(SCHEMA["properties"]["rera"]["properties"])


def _seed() -> pd.DataFrame:
    # project_name is a real normalized column that the snapshot schema does not allow.
    return pd.DataFrame([
        {
            "district": "Vellore",
            "project_name": "Example Project",
            "rera_registration_number": "TN/00/Example/0001",
            "promoter_name": "Example Promoter",
            "registered_completion_date": "2027-03-31T00:00:00",
            "source_url": "https://example.invalid/project",
        }
    ])


def test_district_match_is_candidate_evidence_not_registration() -> None:
    """A shared district must never be reported as this parcel's registration."""
    match = match_parcel_to_rera("vellore", _seed())
    assert match["rera"]["is_rera_project"] is None, "district match must stay unknown, not True"
    assert all(match["rera"][field] is None for field in RERA_SNAPSHOT_FIELDS), (
        "another project's registration must not be copied onto this parcel"
    )
    assert match["district_match_count"] == 1
    candidate = match["district_candidate"]
    assert candidate["rera_registration_number"] == "TN/00/Example/0001"
    assert candidate["registered_completion_date"] == "2027-03-31"


def test_rera_block_only_emits_schema_fields() -> None:
    for district in ("vellore", "Chennai", None):
        rera = match_parcel_to_rera(district, _seed())["rera"]
        assert set(rera) <= ALLOWED, "rera block leaked a field the snapshot schema rejects"


def test_absence_from_seed_is_unknown_not_negative() -> None:
    """The seed is one state's partial export; absence proves nothing."""
    for district in ("Chennai", None):
        match = match_parcel_to_rera(district, _seed())
        assert match["rera"]["is_rera_project"] is None
        assert match["district_candidate"] is None
        assert match["district_match_count"] == 0


if __name__ == "__main__":
    test_district_match_is_candidate_evidence_not_registration()
    test_rera_block_only_emits_schema_fields()
    test_absence_from_seed_is_unknown_not_negative()
    print("rera_ingest checks passed")
