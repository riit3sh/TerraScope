"""The land-price CSV import contract: validation, unit normalization, dedupe.

See README.md for the column contract and the dataset requirements.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pandas as pd


REQUIRED_COLUMNS = (
    "record_id",
    "latitude",
    "longitude",
    "district",
    "state",
    "area_value",
    "area_unit",
    "land_use",
    "observation_date",
    "price_value",
    "price_unit",
    "price_basis",
    "source",
)

# Area units are converted to square feet. Regional units whose size is not
# nationally fixed (bigha, katha) are deliberately absent: accepting them would
# silently mix incompatible areas. Supply those rows pre-converted to sqft.
AREA_UNITS_IN_SQFT: dict[str, float] = {
    "sqft": 1.0,
    "sqyd": 9.0,
    "sqm": 10.763910416709722,
    "acre": 43560.0,
    "hectare": 107639.10416709722,
    "cent": 435.6,
    "guntha": 1089.0,
    "ground": 2400.0,
    "kanal": 5445.0,
    "marla": 272.25,
}

LAND_USES = ("residential", "commercial", "industrial", "agricultural", "mixed_use")
PRICE_BASES = ("asking", "transaction")
PRICE_UNITS = ("total_inr", "inr_per_sqft", "inr_per_sqm", "inr_per_acre", "inr_per_cent")

# Guards against decimal-place errors and currency mix-ups in a scraped export.
MIN_PLAUSIBLE_INR_PER_SQFT = 1.0
MAX_PLAUSIBLE_INR_PER_SQFT = 500_000.0


class DatasetError(ValueError):
    """Raised when an imported CSV does not satisfy the documented contract."""


@dataclass
class ImportReport:
    """What the importer kept, what it dropped, and why."""

    rows_read: int = 0
    rows_kept: int = 0
    dropped: dict[str, int] = field(default_factory=dict)
    duplicate_properties_collapsed: int = 0

    def drop(self, reason: str, count: int) -> None:
        if count:
            self.dropped[reason] = self.dropped.get(reason, 0) + int(count)

    def as_dict(self) -> dict[str, Any]:
        return {
            "rows_read": self.rows_read,
            "rows_kept": self.rows_kept,
            "dropped": dict(self.dropped),
            "duplicate_properties_collapsed": self.duplicate_properties_collapsed,
        }


def _normalize_header(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(value).strip().lower()).strip("_")


def property_key(row: pd.Series) -> str:
    """Identify the physical property, so re-listings cannot straddle a split.

    Coordinates are rounded to ~11 m and area to the nearest 10 sqft: the same
    plot re-advertised at a new price collapses onto one key, which keeps it out
    of the training and holdout halves at once.
    """
    digest = hashlib.sha1(
        "|".join(
            [
                f"{float(row['latitude']):.4f}",
                f"{float(row['longitude']):.4f}",
                f"{round(float(row['area_sqft']) / 10.0):d}",
                str(row["land_use"]),
            ]
        ).encode("utf-8")
    )
    return digest.hexdigest()[:16]


def load_price_csv(csv_path: str | Path) -> tuple[pd.DataFrame, ImportReport]:
    """Load, validate and normalize a land-price CSV into modelling units.

    Returns rows carrying ``area_sqft``, ``price_inr_per_sqft`` and
    ``property_key``, plus a report of everything dropped on the way.
    """
    path = Path(csv_path)
    if not path.exists():
        raise DatasetError(f"Land-price dataset not found: {path}")
    frame = pd.read_csv(path, dtype=str, keep_default_na=False)
    frame.columns = [_normalize_header(column) for column in frame.columns]
    report = ImportReport(rows_read=len(frame))

    missing = [column for column in REQUIRED_COLUMNS if column not in frame.columns]
    if missing:
        raise DatasetError(
            f"Land-price dataset is missing required columns: {missing}. "
            f"Required contract: {list(REQUIRED_COLUMNS)}"
        )
    if frame.empty:
        raise DatasetError(f"Land-price dataset has no rows: {path}")

    frame = frame.loc[:, list(REQUIRED_COLUMNS)].copy()
    for column in ("area_unit", "land_use", "price_unit", "price_basis"):
        frame[column] = frame[column].str.strip().str.lower()
    for column in ("district", "state", "source", "record_id"):
        frame[column] = frame[column].str.strip()

    for column in ("latitude", "longitude", "area_value", "price_value"):
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    frame["observation_date"] = pd.to_datetime(
        frame["observation_date"], errors="coerce", format="mixed"
    )

    def drop_rows(mask: pd.Series, reason: str) -> None:
        nonlocal frame
        bad = int(mask.sum())
        if bad:
            report.drop(reason, bad)
            frame = frame.loc[~mask].copy()

    drop_rows(
        frame[["latitude", "longitude", "area_value", "price_value"]].isna().any(axis=1),
        "non_numeric_or_missing_values",
    )
    drop_rows(frame["observation_date"].isna(), "unparseable_observation_date")
    drop_rows(
        ~frame["latitude"].between(-90, 90) | ~frame["longitude"].between(-180, 180),
        "coordinates_out_of_range",
    )
    drop_rows(frame["area_value"] <= 0, "non_positive_area")
    drop_rows(frame["price_value"] <= 0, "non_positive_price")
    drop_rows(~frame["area_unit"].isin(AREA_UNITS_IN_SQFT), "unsupported_area_unit")
    drop_rows(~frame["price_unit"].isin(PRICE_UNITS), "unsupported_price_unit")
    drop_rows(~frame["land_use"].isin(LAND_USES), "unsupported_land_use")
    drop_rows(~frame["price_basis"].isin(PRICE_BASES), "unsupported_price_basis")

    if frame.empty:
        raise DatasetError(
            f"No rows in {path.name} satisfied the import contract: {report.as_dict()}"
        )

    frame["area_sqft"] = frame["area_value"] * frame["area_unit"].map(AREA_UNITS_IN_SQFT)
    converters = {
        "inr_per_sqft": lambda f: f["price_value"],
        "inr_per_sqm": lambda f: f["price_value"] / AREA_UNITS_IN_SQFT["sqm"],
        "inr_per_acre": lambda f: f["price_value"] / AREA_UNITS_IN_SQFT["acre"],
        "inr_per_cent": lambda f: f["price_value"] / AREA_UNITS_IN_SQFT["cent"],
        "total_inr": lambda f: f["price_value"] / f["area_sqft"],
    }
    frame["price_inr_per_sqft"] = 0.0
    for unit, convert in converters.items():
        rows = frame["price_unit"] == unit
        if rows.any():
            frame.loc[rows, "price_inr_per_sqft"] = convert(frame.loc[rows])

    drop_rows(
        ~frame["price_inr_per_sqft"].between(
            MIN_PLAUSIBLE_INR_PER_SQFT, MAX_PLAUSIBLE_INR_PER_SQFT, inclusive="both"
        ),
        "price_per_sqft_outside_plausible_range",
    )
    if frame.empty:
        raise DatasetError(f"No rows in {path.name} survived normalization: {report.as_dict()}")

    frame["property_key"] = frame.apply(property_key, axis=1)
    before = len(frame)
    # Keep the most recent observation per physical property.
    frame = (
        frame.sort_values("observation_date")
        .drop_duplicates(subset=["property_key"], keep="last")
        .reset_index(drop=True)
    )
    report.duplicate_properties_collapsed = before - len(frame)
    report.rows_kept = len(frame)
    return frame, report


def dataset_version(frame: pd.DataFrame) -> str:
    """Content hash of the normalized rows, so a prediction names its data."""
    payload = pd.util.hash_pandas_object(
        frame[["property_key", "price_inr_per_sqft", "observation_date"]], index=False
    ).values.tobytes()
    return hashlib.sha256(payload).hexdigest()[:12]
