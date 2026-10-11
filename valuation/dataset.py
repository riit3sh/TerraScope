"""Land-price observations: the import contract, unit normalisation and cleaning.

One row is one price observation of one property. Three price types are kept
apart and never pooled:

- ``asking``: a seller's asking price from a listing. Not a sale price.
- ``transaction``: a price observed in a completed, registered sale.
- ``guideline``: a government guideline / circle / reference rate (an
  administrative floor for stamp duty, not a market price).

Every dropped row is counted by reason in the import report; nothing is
silently repaired. See README.md for the column contract.
"""

from __future__ import annotations

import hashlib
import math
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


REQUIRED_COLUMNS = (
    "source", "source_record_id", "reuse_basis", "price_type", "observed_date", "retrieved_date",
    "price_value", "price_unit", "currency", "property_category", "land_use",
    "latitude", "longitude", "location_precision",
)
# property_ref: a stable identifier of the plot when the source has one (survey or plot
# number, layout reference). Rows sharing it within a district are one property.
OPTIONAL_COLUMNS = ("source_url", "area_value", "area_unit", "district", "state", "locality", "attributes",
                    "property_ref")

PRICE_TYPES = ("asking", "transaction", "guideline")
PRICE_TYPE_LABELS = {
    "asking": "seller asking prices (listings), not completed sales",
    "transaction": "completed, registered sale prices",
    "guideline": "government guideline / reference rates (administrative floors, not market prices)",
}
LAND_USES = ("residential", "commercial", "industrial", "agricultural", "mixed_use")
# Only vacant land is comparable to a land parcel. Apartments, houses and buildings
# carry construction value and are excluded, never mixed in.
LAND_CATEGORIES = ("vacant_plot", "agricultural_land")
BUILT_CATEGORIES = ("apartment", "independent_house", "villa", "commercial_building", "other")
LOCATION_PRECISIONS = ("exact", "street", "locality", "pincode", "district")
COMPARABLE_PRECISIONS = ("exact", "street", "locality")

# Area units to square feet. bigha, katha and similar units vary by state and
# district, so they are rejected rather than converted with a guessed factor.
AREA_UNITS_IN_SQFT: dict[str, float] = {
    "sqft": 1.0, "sqm": 10.763910416709722, "sqyd": 9.0, "acre": 43560.0, "hectare": 107639.10416709722,
    "cent": 435.6, "guntha": 1089.0, "ground": 2400.0, "kanal": 5445.0, "marla": 272.25,
}
# A price unit is "total" or "per_<area unit>".
PRICE_UNITS = ("total",) + tuple(f"per_{unit}" for unit in AREA_UNITS_IN_SQFT)

# Plausibility bounds catch decimal-place, unit and currency mistakes. Generous on
# purpose: they reject impossible rows, not merely unusual ones.
PLAUSIBLE_INR_PER_SQFT = {"vacant_plot": (20.0, 300_000.0), "agricultural_land": (1.0, 20_000.0)}
PLAUSIBLE_AREA_SQFT = {"vacant_plot": (200.0, 50 * 43560.0), "agricultural_land": (0.05 * 43560.0, 1000 * 43560.0)}
INDIA_BBOX = (6.0, 38.5, 67.5, 98.0)  # lat min, lat max, lon min, lon max

# Same plot re-advertised (by another broker, re-posted, or listed again a year later)
# must count once, or it would be its own comparable and could sit on both sides of a
# validation split. Exact points: within 25 m (layout plots are ~9-12 m apart, so a
# wider radius would merge neighbours) and area within 3%, at any date.
DUPLICATE_DISTANCE_M = 25.0
DUPLICATE_AREA_TOLERANCE = 0.03
# Street- or locality-level points share coordinates with other plots, so they also
# need a matching price, within a year.
COARSE_DUPLICATE_DISTANCE_M = 75.0
COARSE_DUPLICATE_AREA_TOLERANCE = 0.01
COARSE_DUPLICATE_PRICE_TOLERANCE = 0.03
COARSE_DUPLICATE_WINDOW_DAYS = 365


class DatasetError(ValueError):
    """The file does not satisfy the import contract at all."""


@dataclass
class ImportReport:
    rows_read: int = 0
    rows_kept: int = 0
    dropped: dict[str, int] = field(default_factory=dict)
    same_record_repeated: int = 0
    duplicate_listings_collapsed: int = 0

    def drop(self, reason: str, count: int) -> None:
        if count:
            self.dropped[reason] = self.dropped.get(reason, 0) + int(count)

    def as_dict(self) -> dict[str, Any]:
        return {
            "rows_read": self.rows_read,
            "rows_kept": self.rows_kept,
            "dropped": dict(sorted(self.dropped.items())),
            "same_record_repeated": self.same_record_repeated,
            "duplicate_listings_collapsed": self.duplicate_listings_collapsed,
        }


def _header(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(value).strip().lower()).strip("_")


def haversine_m(lat1, lon1, lat2, lon2):
    """Great-circle distance in metres; works on scalars and numpy arrays."""
    p1, p2 = np.radians(lat1), np.radians(lat2)
    a = np.sin((p2 - p1) / 2) ** 2 + np.cos(p1) * np.cos(p2) * np.sin(np.radians(lon2 - lon1) / 2) ** 2
    return 2 * 6_371_008.8 * np.arcsin(np.sqrt(a))


def normalize(frame: pd.DataFrame) -> tuple[pd.DataFrame, ImportReport]:
    """Validate, convert units and de-duplicate raw observation rows.

    Adds ``area_sqft`` (NaN when the row has no area), ``price_inr_per_sqft``,
    and ``group_id`` / ``group_size`` / ``group_sources`` for re-listings of one
    property, keeping one representative row per group.
    """
    report = ImportReport(rows_read=len(frame))
    frame = frame.copy()
    frame.columns = [_header(column) for column in frame.columns]
    missing = [column for column in REQUIRED_COLUMNS if column not in frame.columns]
    if missing:
        raise DatasetError(f"Missing required columns {missing}. Contract: {list(REQUIRED_COLUMNS)}")
    for column in OPTIONAL_COLUMNS:
        if column not in frame.columns:
            frame[column] = ""
    frame = frame.loc[:, list(REQUIRED_COLUMNS + OPTIONAL_COLUMNS)].astype(str).apply(lambda c: c.str.strip())
    for column in ("price_type", "price_unit", "currency", "property_category", "land_use", "location_precision", "area_unit"):
        frame[column] = frame[column].str.lower()

    def drop(mask: pd.Series, reason: str) -> None:
        nonlocal frame
        report.drop(reason, int(mask.sum()))
        frame = frame.loc[~mask]

    drop((frame[["source", "source_record_id"]] == "").any(axis=1), "missing_source_or_record_id")
    drop(frame["reuse_basis"] == "", "missing_reuse_basis")
    drop(~frame["price_type"].isin(PRICE_TYPES), "unknown_price_type")
    drop(frame["currency"] != "inr", "currency_not_inr")  # never converted at a guessed exchange rate
    drop(~frame["price_unit"].isin(PRICE_UNITS), "unsupported_price_unit")
    drop(frame["property_category"].isin(BUILT_CATEGORIES), "not_vacant_land")
    drop(~frame["property_category"].isin(LAND_CATEGORIES), "unknown_property_category")
    drop(~frame["land_use"].isin(LAND_USES), "unknown_land_use")
    drop((frame["property_category"] == "agricultural_land") != (frame["land_use"] == "agricultural"),
         "category_land_use_mismatch")
    drop(~frame["location_precision"].isin(LOCATION_PRECISIONS), "unknown_location_precision")

    for column in ("latitude", "longitude", "price_value", "area_value"):
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    for column in ("observed_date", "retrieved_date"):
        frame[column] = pd.to_datetime(frame[column], errors="coerce", format="mixed")
    drop(frame[["latitude", "longitude"]].isna().any(axis=1), "missing_coordinates")
    lat_min, lat_max, lon_min, lon_max = INDIA_BBOX
    drop(~frame["latitude"].between(lat_min, lat_max) | ~frame["longitude"].between(lon_min, lon_max),
         "coordinates_outside_india")
    drop(frame[["observed_date", "retrieved_date"]].isna().any(axis=1), "unparseable_date")
    drop(frame["retrieved_date"] < frame["observed_date"], "retrieved_before_observed")
    drop(~(frame["price_value"] > 0), "non_positive_price")

    has_area = frame["area_value"].notna() | (frame["area_unit"] != "")
    drop(has_area & ~((frame["area_value"] > 0) & frame["area_unit"].isin(AREA_UNITS_IN_SQFT)), "invalid_area")
    drop((frame["price_unit"] == "total") & frame["area_value"].isna(), "total_price_without_area")
    if frame.empty:
        raise DatasetError(f"No rows satisfied the import contract: {report.as_dict()}")

    frame["area_sqft"] = frame["area_value"] * frame["area_unit"].map(AREA_UNITS_IN_SQFT)
    per_unit = frame["price_unit"].str.removeprefix("per_").map(AREA_UNITS_IN_SQFT)
    frame["price_inr_per_sqft"] = np.where(
        frame["price_unit"] == "total", frame["price_value"] / frame["area_sqft"], frame["price_value"] / per_unit
    )
    for category, (low, high) in PLAUSIBLE_INR_PER_SQFT.items():
        drop((frame["property_category"] == category) & ~frame["price_inr_per_sqft"].between(low, high),
             "implausible_price_per_sqft")
    for category, (low, high) in PLAUSIBLE_AREA_SQFT.items():
        drop((frame["property_category"] == category) & frame["area_sqft"].notna()
             & ~frame["area_sqft"].between(low, high), "implausible_area")
    if frame.empty:
        raise DatasetError(f"No rows survived cleaning: {report.as_dict()}")

    # The same record delivered twice (re-import, overlapping exports): keep the latest retrieval.
    before = len(frame)
    frame = frame.sort_values("retrieved_date").drop_duplicates(["source", "source_record_id"], keep="last")
    report.same_record_repeated = before - len(frame)

    frame = _collapse_duplicate_listings(frame.reset_index(drop=True), report)
    report.rows_kept = len(frame)
    return frame, report


def _collapse_duplicate_listings(frame: pd.DataFrame, report: ImportReport) -> pd.DataFrame:
    """Group re-listings of one property (any source) and keep the most recent observation."""
    parent = list(range(len(frame)))

    def root(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    lat, lon = frame["latitude"].to_numpy(), frame["longitude"].to_numpy()
    area, price = frame["area_sqft"].to_numpy(dtype=float), frame["price_inr_per_sqft"].to_numpy(dtype=float)
    days = frame["observed_date"].to_numpy().astype("datetime64[D]").astype(np.int64)
    coarse = (frame["location_precision"] != "exact").to_numpy()
    refs = (frame["district"].str.casefold() + "|" + frame["property_ref"].str.casefold()).where(
        frame["property_ref"] != "", "").to_numpy()
    kind = (frame["price_type"] + "|" + frame["property_category"] + "|" + frame["land_use"]).to_numpy()

    # A source-supplied plot identifier is the strongest evidence of one property.
    referenced = frame[frame["property_ref"] != ""]
    for _, rows in referenced.groupby([kind[referenced.index], referenced["district"].str.casefold(),
                                       referenced["property_ref"].str.casefold()]):
        for j in rows.index[1:]:
            parent[root(j)] = root(rows.index[0])

    # ponytail: ~110 m grid buckets with a pairwise check inside each 3x3 block;
    # fine for 10^5 rows, use a KD-tree if a feed ever reaches 10^6.
    buckets: dict[tuple, list[int]] = {}
    for i in range(len(frame)):
        buckets.setdefault((kind[i], math.floor(lat[i] * 1000), math.floor(lon[i] * 1000)), []).append(i)
    for (k, y, x), members in buckets.items():
        neighbours = [j for dy in (-1, 0, 1) for dx in (-1, 0, 1) for j in buckets.get((k, y + dy, x + dx), [])]
        for i in members:
            for j in neighbours:
                if j <= i or np.isnan(area[i]) or np.isnan(area[j]):
                    continue  # without areas two rows cannot be shown to be one plot
                if refs[i] and refs[j] and refs[i] != refs[j]:
                    continue  # different plot identifiers: neighbours, not re-listings
                tight = coarse[i] or coarse[j]
                if tight and abs(days[i] - days[j]) > COARSE_DUPLICATE_WINDOW_DAYS:
                    continue
                if haversine_m(lat[i], lon[i], lat[j], lon[j]) > (COARSE_DUPLICATE_DISTANCE_M if tight else DUPLICATE_DISTANCE_M):
                    continue
                tolerance = COARSE_DUPLICATE_AREA_TOLERANCE if tight else DUPLICATE_AREA_TOLERANCE
                if abs(area[i] - area[j]) > tolerance * max(area[i], area[j]):
                    continue
                if tight and abs(price[i] - price[j]) > COARSE_DUPLICATE_PRICE_TOLERANCE * max(price[i], price[j]):
                    continue
                parent[root(i)] = root(j)
    roots = pd.Series([root(i) for i in range(len(frame))], index=frame.index)
    frame["group_size"] = roots.map(roots.value_counts())
    frame["group_sources"] = roots.map(frame.groupby(roots)["source"].agg(lambda s: "; ".join(sorted(set(s)))))
    keys = frame["source"] + "|" + frame["source_record_id"]
    frame["group_id"] = roots.map(lambda r: hashlib.sha1(keys.iat[r].encode()).hexdigest()[:12])
    kept = frame.sort_values(["observed_date", "retrieved_date"]).drop_duplicates("group_id", keep="last")
    report.duplicate_listings_collapsed = len(frame) - len(kept)
    return kept.sort_values("observed_date").reset_index(drop=True)


def load_observations(path: str | Path) -> tuple[pd.DataFrame, ImportReport]:
    path = Path(path)
    if not path.exists():
        raise DatasetError(f"Price observations not found: {path}")
    raw = pd.read_csv(path, dtype=str, keep_default_na=False)
    if raw.empty:
        raise DatasetError(f"{path.name} has no rows.")
    return normalize(raw)


def dataset_version(frame: pd.DataFrame) -> str:
    """Content hash of the cleaned rows, so an estimate names the data behind it."""
    payload = pd.util.hash_pandas_object(
        frame[["source", "source_record_id", "price_inr_per_sqft", "observed_date"]], index=False
    ).values.tobytes()
    return hashlib.sha256(payload).hexdigest()[:12]


def summary(frame: pd.DataFrame) -> dict[str, Any]:
    return {
        "rows": int(len(frame)),
        "price_types": {k: int(v) for k, v in frame["price_type"].value_counts().items()},
        "categories": {k: int(v) for k, v in frame["property_category"].value_counts().items()},
        "land_uses": {k: int(v) for k, v in frame["land_use"].value_counts().items()},
        "states": sorted(s for s in frame["state"].unique() if s),
        "districts": int(frame["district"].replace("", np.nan).nunique()),
        "sources": sorted(frame["source"].unique().tolist()),
        "observed_from": frame["observed_date"].min().date().isoformat(),
        "observed_to": frame["observed_date"].max().date().isoformat(),
        "location_precision": {k: int(v) for k, v in frame["location_precision"].value_counts().items()},
    }


if __name__ == "__main__":
    import argparse
    import json

    parser = argparse.ArgumentParser(description="Validate a land-price observations CSV and print the import report.")
    parser.add_argument("csv")
    args = parser.parse_args()
    cleaned, import_report = load_observations(args.csv)
    print(json.dumps({"import": import_report.as_dict(), "kept": summary(cleaned)}, indent=2))
