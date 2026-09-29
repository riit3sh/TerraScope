"""Small SQLite persistence layer for backend snapshots and evaluation history."""

from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _path() -> Path:
    return Path(os.getenv("BACKEND_STORE_PATH", "/tmp/terrascope_backend.sqlite3"))


def _connect() -> sqlite3.Connection:
    path = _path()
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    return connection


def init_store() -> None:
    with _connect() as connection:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS snapshots (
                snapshot_id TEXT PRIMARY KEY,
                parcel_id TEXT NOT NULL,
                snapshot_json TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS evaluation_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                parcel_id TEXT NOT NULL,
                snapshot_id TEXT NOT NULL,
                evaluation_json TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS documents (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                parcel_id TEXT NOT NULL,
                filename TEXT NOT NULL,
                content_type TEXT NOT NULL,
                size_bytes INTEGER NOT NULL,
                text_content TEXT,
                created_at TEXT NOT NULL
            );
            """
        )


def save_snapshot(snapshot: dict[str, Any]) -> None:
    snapshot_id = snapshot["metadata"]["analysis_snapshot_id"]
    parcel_id = snapshot["parcel_id"]
    with _connect() as connection:
        connection.execute(
            "INSERT OR IGNORE INTO snapshots(snapshot_id, parcel_id, snapshot_json, created_at) VALUES (?, ?, ?, ?)",
            (snapshot_id, parcel_id, json.dumps(snapshot), datetime.now(timezone.utc).isoformat()),
        )


def get_snapshot(snapshot_id: str) -> dict[str, Any] | None:
    with _connect() as connection:
        row = connection.execute("SELECT snapshot_json FROM snapshots WHERE snapshot_id = ?", (snapshot_id,)).fetchone()
    return json.loads(row["snapshot_json"]) if row else None


def get_latest_for_parcel(parcel_id: str) -> tuple[str, dict[str, Any]] | None:
    with _connect() as connection:
        row = connection.execute(
            "SELECT snapshot_id, snapshot_json FROM snapshots WHERE parcel_id = ? ORDER BY created_at DESC LIMIT 1",
            (parcel_id,),
        ).fetchone()
    return (row["snapshot_id"], json.loads(row["snapshot_json"])) if row else None


def list_saved_reports(limit: int = 50) -> list[dict[str, Any]]:
    """Most recent snapshot per parcel, for the saved-reports list."""
    with _connect() as connection:
        rows = connection.execute(
            """
            SELECT s.parcel_id, s.snapshot_id, s.snapshot_json, s.created_at,
                   (SELECT COUNT(*) FROM documents d WHERE d.parcel_id = s.parcel_id) AS document_count
            FROM snapshots s
            JOIN (SELECT parcel_id, MAX(created_at) AS newest FROM snapshots GROUP BY parcel_id) latest
              ON latest.parcel_id = s.parcel_id AND latest.newest = s.created_at
            ORDER BY s.created_at DESC LIMIT ?
            """,
            (int(limit),),
        ).fetchall()
    reports = []
    for row in rows:
        snapshot = json.loads(row["snapshot_json"])
        location = snapshot.get("location") or {}
        metadata = snapshot.get("metadata") or {}
        geometry = snapshot.get("geometry_metadata") or {}
        reports.append({
            "parcel_id": row["parcel_id"],
            "analysis_snapshot_id": row["snapshot_id"],
            "created_at": row["created_at"],
            "address": location.get("address"),
            "district": location.get("district"),
            "area_acres": geometry.get("area_acres"),
            "analysis_date_from": metadata.get("analysis_date_from"),
            "analysis_date_to": metadata.get("analysis_date_to"),
            "document_count": int(row["document_count"] or 0),
            "has_evaluation": get_latest_evaluation(row["parcel_id"]) is not None,
        })
    return reports


def save_evaluation(parcel_id: str, snapshot_id: str, evaluation: dict[str, Any]) -> None:
    with _connect() as connection:
        connection.execute(
            "INSERT INTO evaluation_history(parcel_id, snapshot_id, evaluation_json, created_at) VALUES (?, ?, ?, ?)",
            (parcel_id, snapshot_id, json.dumps(evaluation), datetime.now(timezone.utc).isoformat()),
        )


def get_latest_evaluation(parcel_id: str) -> dict[str, Any] | None:
    with _connect() as connection:
        row = connection.execute(
            "SELECT evaluation_json FROM evaluation_history WHERE parcel_id = ? ORDER BY id DESC LIMIT 1",
            (parcel_id,),
        ).fetchone()
    return json.loads(row["evaluation_json"]) if row else None


def save_document(parcel_id: str, filename: str, content_type: str, size_bytes: int, text_content: str | None) -> int:
    with _connect() as connection:
        cursor = connection.execute(
            "INSERT INTO documents(parcel_id, filename, content_type, size_bytes, text_content, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (parcel_id, filename, content_type, size_bytes, text_content, datetime.now(timezone.utc).isoformat()),
        )
        return int(cursor.lastrowid)


def get_document_texts(parcel_id: str) -> list[dict[str, str]]:
    with _connect() as connection:
        rows = connection.execute(
            "SELECT filename, content_type, text_content FROM documents WHERE parcel_id = ? ORDER BY id",
            (parcel_id,),
        ).fetchall()
    return [
        {
            "text": row["text_content"],
            "source_type": "user_upload",
            "source_reference": row["filename"],
            "parcel_id": parcel_id,
        }
        for row in rows
        if row["text_content"]
    ]

