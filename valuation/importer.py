"""Preview, then add, owner/broker-supplied or licensed price rows to the served observations file.

Preview never writes. It reports every row's fate: rejected (with the reason), a repeat of
another row, a re-listing of the same plot, stale for today's estimates, or usable. Commit
appends only rows that passed validation, keeps a timestamped backup of the previous file,
and re-validates the combined file before replacing it, so a bad import cannot break the
estimates already being served.
"""

from __future__ import annotations

import io
import shutil
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from .comparables import MAX_AGE_DAYS
from .dataset import COMPARABLE_PRECISIONS, DatasetError, _header, normalize

PREVIEW_ROWS = 50


def read_csv(content: bytes | str | Path) -> pd.DataFrame:
    source = content if isinstance(content, Path) else io.BytesIO(
        content.encode("utf-8") if isinstance(content, str) else content)
    raw = pd.read_csv(source, dtype=str, keep_default_na=False)
    raw.columns = [_header(column) for column in raw.columns]
    return raw


def preview(raw: pd.DataFrame, today: date | None = None) -> dict[str, Any]:
    """What an import would add, row by row. Nothing is written."""
    today = today or datetime.now(timezone.utc).date()
    try:
        frame, report = normalize(raw)
    except DatasetError as error:
        return {"ok": False, "error": str(error), "rows_read": len(raw)}
    when = pd.Timestamp(today)
    age_days = (when - frame["observed_date"]).dt.days
    stale = age_days > frame["price_type"].map(MAX_AGE_DAYS)
    future = frame["observed_date"] > when
    usable = ~stale & ~future & frame["location_precision"].isin(COMPARABLE_PRECISIONS)
    groups = (
        frame.assign(usable=usable)
        .groupby(["price_type", "land_use", "property_category"])
        .agg(rows=("csv_row", "size"), usable_now=("usable", "sum"),
             median_inr_per_sqft=("price_inr_per_sqft", "median"),
             observed_from=("observed_date", "min"), observed_to=("observed_date", "max"))
        .reset_index()
    )
    return {
        "ok": True,
        "rows_read": report.rows_read,
        "rows_valid": report.rows_kept,
        "rejected": report.rejected_rows,
        "duplicates": report.duplicate_rows,
        "stale_rows": [int(row) for row in frame.loc[stale, "csv_row"]],
        "future_rows": [int(row) for row in frame.loc[future, "csv_row"]],
        "coarse_location_rows": [int(row) for row in frame.loc[~frame["location_precision"].isin(COMPARABLE_PRECISIONS), "csv_row"]],
        "usable_as_comparables_today": int(usable.sum()),
        # Price bases, land uses and categories are never pooled; each is its own group.
        "groups": [
            {**{key: row[key] for key in ("price_type", "land_use", "property_category")},
             "rows": int(row["rows"]), "usable_now": int(row["usable_now"]),
             "median_inr_per_sqft": round(float(row["median_inr_per_sqft"]), 2),
             "observed_from": row["observed_from"].date().isoformat(), "observed_to": row["observed_to"].date().isoformat()}
            for _, row in groups.iterrows()
        ],
        "sources": [
            {"source": source, "reuse_basis": sorted(rows["reuse_basis"].unique().tolist()), "rows": int(len(rows))}
            for source, rows in frame.groupby("source")
        ],
        "location_precision": {key: int(value) for key, value in frame["location_precision"].value_counts().items()},
        "rows": [
            {"row": int(row["csv_row"]), "source": row["source"], "source_record_id": row["source_record_id"],
             "price_type": row["price_type"], "land_use": row["land_use"], "property_category": row["property_category"],
             "observed_date": row["observed_date"].date().isoformat(),
             "price_inr_per_sqft": round(float(row["price_inr_per_sqft"]), 2),
             "area_sqft": None if pd.isna(row["area_sqft"]) else round(float(row["area_sqft"]), 1),
             "location_precision": row["location_precision"], "locality": row["locality"] or None,
             "reuse_basis": row["reuse_basis"],
             "flags": [flag for flag, on in (("stale", bool(stale[index])), ("future_date", bool(future[index])),
                                             ("coarse_location", row["location_precision"] not in COMPARABLE_PRECISIONS),
                                             ("re-listed", int(row["group_size"]) > 1)) if on]}
            for index, row in frame.sort_values("csv_row").head(PREVIEW_ROWS).iterrows()
        ],
    }


def commit(raw: pd.DataFrame, path: Path, today: date | None = None) -> dict[str, Any]:
    """Append the rows that pass validation; back up and re-validate before replacing the served file."""
    result = preview(raw, today)
    if not result["ok"]:
        raise DatasetError(result["error"])
    rejected = {item["row"] for item in result["rejected"]}
    batch = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    keep = raw.iloc[[index for index in range(len(raw)) if index + 2 not in rejected]].assign(imported_at=batch)
    existing = read_csv(path) if path.exists() else pd.DataFrame()
    combined = pd.concat([existing, keep], ignore_index=True).fillna("")
    normalize(combined)  # raises before anything is replaced
    path.parent.mkdir(parents=True, exist_ok=True)
    backup = None
    if path.exists():
        backup = path.with_name(f"{path.name}.bak-{batch.replace(':', '')}")
        shutil.copy2(path, backup)
    staging = path.with_name(f"{path.name}.importing")
    combined.to_csv(staging, index=False)
    staging.replace(path)
    return {"rows_added": len(keep), "rows_rejected": len(rejected), "rows_in_file": len(combined),
            "imported_at": batch, "backup": backup.name if backup else None, "preview": result}
