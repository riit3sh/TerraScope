"""RERA has no public national API; each state runs its own portal. This module uses a static seed dataset (MahaRERA) for the POC, matched by district only. Production scope: per-state scrapers + fuzzy project-name matching — see roadmap."""

from __future__ import annotations

import re
from datetime import date, datetime
from pathlib import Path
from typing import Any

import pandas as pd


# Common MahaRERA/Kaggle header variants are normalized to these stable fields.
_COLUMN_ALIASES: dict[str, set[str]] = {
    "district": {"district", "district_name", "districtname"},
    "project_name": {"project_name", "projectname", "name_of_project", "project"},
    "rera_registration_number": {
        "rera_registration_number",
        "registration_number",
        "registration_no",
        "rera_registration_no",
        "registrationnumber",
    },
    "promoter_name": {"promoter_name", "promotername", "name_of_promoter", "promoter"},
    "registered_completion_date": {
        "registered_completion_date",
        "completion_date",
        "proposed_completion_date",
        "completiondate",
    },
    "source_url": {"source_url", "project_url", "url", "website"},
}


# Only these fields are allowed through to the evidence snapshot (see docs/schema/parcel_schema.json).
RERA_SNAPSHOT_FIELDS = ("rera_registration_number", "promoter_name", "registered_completion_date", "source_url")


def _normalize_header(value: Any) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "_", str(value).strip().lower()).strip("_")
    return normalized


def _canonicalize_columns(dataframe: pd.DataFrame) -> pd.DataFrame:
    renamed: dict[Any, str] = {}
    used_canonical: set[str] = set()
    aliases_to_canonical = {
        alias: canonical for canonical, aliases in _COLUMN_ALIASES.items() for alias in aliases
    }
    for original in dataframe.columns:
        normalized = _normalize_header(original)
        canonical = aliases_to_canonical.get(normalized, normalized)
        # Keep the first matching source column if a CSV contains duplicate aliases.
        if canonical in used_canonical:
            continue
        renamed[original] = canonical
        used_canonical.add(canonical)
    return dataframe.loc[:, list(renamed)].rename(columns=renamed)


def _clean_value(value: Any) -> Any:
    if isinstance(value, str):
        stripped = value.strip()
        return stripped if stripped else pd.NA
    return value


def _json_safe(value: Any) -> Any:
    if value is None or value is pd.NA:
        return None
    if isinstance(value, (pd.Timestamp, datetime, date)):
        return value.isoformat()
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    return value


def load_rera_seed_dataset(csv_path: str | Path) -> pd.DataFrame:
    """Load and clean the static MahaRERA seed CSV.

    Headers are normalized to snake_case and common Kaggle field variants are
    mapped to stable names such as ``district`` and ``project_name``.
    Date-like columns are parsed with invalid values becoming ``NaT``.
    """
    path = Path(csv_path)
    try:
        dataframe = pd.read_csv(path, dtype=str, keep_default_na=False)
    except FileNotFoundError:
        raise FileNotFoundError(f"RERA seed dataset not found: {path}") from None

    dataframe = _canonicalize_columns(dataframe)
    dataframe = dataframe.apply(lambda column: column.map(_clean_value))
    if "district" not in dataframe.columns:
        raise ValueError(
            "RERA seed dataset must contain a district column. "
            f"Normalized headers found: {list(dataframe.columns)}"
        )

    dataframe["district"] = dataframe["district"].map(
        lambda value: value.title() if isinstance(value, str) else value
    )
    for column in dataframe.columns:
        if "date" in column or column.endswith("_at"):
            dataframe[column] = pd.to_datetime(dataframe[column], errors="coerce", dayfirst=True)
    return dataframe


def match_parcel_to_rera(district: str | None, rera_df: pd.DataFrame) -> dict[str, Any]:
    """Return this parcel's RERA block plus any district-level candidate.

    A district match only proves that *some* registered project shares this
    parcel's district; it is never proof that this parcel is that project. So
    ``rera.is_rera_project`` stays ``None`` (unknown) and the matched project
    travels separately as candidate evidence for the ledger.

    Absence from the seed is equally uninformative -- the seed is one state's
    partial export -- so a non-match is reported as unknown too, never as
    ``False``.
    """
    if not isinstance(rera_df, pd.DataFrame) or "district" not in rera_df.columns:
        raise ValueError("rera_df must be a DataFrame containing a district column.")
    unknown = {"is_rera_project": None, **{field: None for field in RERA_SNAPSHOT_FIELDS}}
    if district is None or not str(district).strip():
        return {"rera": unknown, "district_candidate": None, "district_match_count": 0}

    normalized_district = str(district).strip().casefold()
    district_values = rera_df["district"].map(
        lambda value: str(value).strip().casefold() if pd.notna(value) else ""
    )
    matches = rera_df.loc[district_values == normalized_district]
    if matches.empty:
        return {"rera": unknown, "district_candidate": None, "district_match_count": 0}

    # Exact matching is intentionally simple: a parcel near a registered
    # project may not match if the two sources spell the district differently.
    row = matches.iloc[0].to_dict()
    # The snapshot schema rejects unknown rera fields, so only the shared fields cross the boundary.
    candidate = {field: _json_safe(row.get(field)) for field in RERA_SNAPSHOT_FIELDS}
    completion = candidate.get("registered_completion_date")
    if isinstance(completion, str) and completion:
        candidate["registered_completion_date"] = completion[:10]
    candidate["project_name"] = _json_safe(row.get("project_name"))
    return {"rera": unknown, "district_candidate": candidate, "district_match_count": int(len(matches))}
