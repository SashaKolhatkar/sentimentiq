"""Tiny SQLite persistence layer.

Runs and jobs are stored as JSON documents.  SQLite keeps the local build
zero-config while the repository shape makes a migration to Postgres trivial.
"""

from __future__ import annotations

import json
import sqlite3
import threading
from typing import Any

from .config import DB_PATH
from .utils import to_jsonable, utcnow

_lock = threading.RLock()


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, timeout=30, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db() -> None:
    with _lock, _connect() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS runs (
                id TEXT PRIMARY KEY,
                created_at TEXT NOT NULL,
                name TEXT NOT NULL,
                source_type TEXT NOT NULL,
                is_demo INTEGER NOT NULL DEFAULT 0,
                record_count INTEGER NOT NULL DEFAULT 0,
                summary_json TEXT NOT NULL,
                result_json TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_runs_created ON runs(created_at DESC);

            CREATE TABLE IF NOT EXISTS datasets (
                id TEXT PRIMARY KEY,
                created_at TEXT NOT NULL,
                record_count INTEGER NOT NULL DEFAULT 0,
                source_type TEXT NOT NULL,
                is_demo INTEGER NOT NULL DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS jobs (
                id TEXT PRIMARY KEY,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                status TEXT NOT NULL,
                progress INTEGER NOT NULL DEFAULT 0,
                message TEXT NOT NULL DEFAULT '',
                result_json TEXT,
                error TEXT
            );

            CREATE TABLE IF NOT EXISTS reports (
                id TEXT PRIMARY KEY,
                run_id TEXT NOT NULL,
                format TEXT NOT NULL,
                filename TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY(run_id) REFERENCES runs(id) ON DELETE CASCADE
            );
            """
        )


def _dump(obj: Any) -> str:
    return json.dumps(to_jsonable(obj), ensure_ascii=False, separators=(",", ":"))


def save_run(
    run_id: str,
    name: str,
    source_type: str,
    is_demo: bool,
    result: dict,
    record_count: int | None = None,
) -> None:
    """Persist a run summary. Enriched records live in a streaming JSONL file."""
    summary = result.get("summary", {})
    count = int(record_count if record_count is not None else summary.get("total_records", 0))
    stored = dict(result)
    stored.pop("records", None)
    with _lock, _connect() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO runs "
            "(id, created_at, name, source_type, is_demo, record_count, summary_json, result_json) "
            "VALUES (?,?,?,?,?,?,?,?)",
            (
                run_id,
                utcnow(),
                name[:200],
                source_type,
                int(bool(is_demo)),
                count,
                _dump(summary),
                _dump(stored),
            ),
        )


def get_run(run_id: str) -> dict | None:
    with _lock, _connect() as conn:
        row = conn.execute("SELECT * FROM runs WHERE id = ?", (run_id,)).fetchone()
    if not row:
        return None
    result = json.loads(row["result_json"])
    result["id"] = row["id"]
    result["created_at"] = row["created_at"]
    result["name"] = row["name"]
    result["source_type"] = row["source_type"]
    result["is_demo"] = bool(row["is_demo"])
    return result


def list_runs(limit: int = 50) -> list[dict]:
    with _lock, _connect() as conn:
        rows = conn.execute(
            "SELECT id, created_at, name, source_type, is_demo, record_count, summary_json "
            "FROM runs ORDER BY created_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [
        {
            "id": r["id"],
            "created_at": r["created_at"],
            "name": r["name"],
            "source_type": r["source_type"],
            "is_demo": bool(r["is_demo"]),
            "record_count": r["record_count"],
            "summary": json.loads(r["summary_json"]),
        }
        for r in rows
    ]


def delete_run(run_id: str) -> bool:
    with _lock, _connect() as conn:
        cur = conn.execute("DELETE FROM runs WHERE id = ?", (run_id,))
    return cur.rowcount > 0


def create_job(job_id: str) -> None:
    now = utcnow()
    with _lock, _connect() as conn:
        conn.execute(
            "INSERT INTO jobs (id, created_at, updated_at, status, progress, message) "
            "VALUES (?,?,?,'queued',0,'Queued')",
            (job_id, now, now),
        )


def update_job(
    job_id: str,
    status: str,
    progress: int,
    message: str,
    result: dict | None = None,
    error: str | None = None,
) -> None:
    with _lock, _connect() as conn:
        conn.execute(
            "UPDATE jobs SET updated_at=?, status=?, progress=?, message=?, "
            "result_json=COALESCE(?, result_json), error=? WHERE id=?",
            (
                utcnow(),
                status,
                int(max(0, min(100, progress))),
                message[:500],
                _dump(result) if result is not None else None,
                (error or "")[:1000] or None,
                job_id,
            ),
        )


def get_job(job_id: str) -> dict | None:
    with _lock, _connect() as conn:
        row = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
    if not row:
        return None
    return {
        "id": row["id"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "status": row["status"],
        "progress": row["progress"],
        "message": row["message"],
        "result": json.loads(row["result_json"]) if row["result_json"] else None,
        "error": row["error"],
    }


def create_dataset(dataset_id: str, record_count: int, source_type: str, is_demo: bool) -> None:
    with _lock, _connect() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO datasets (id, created_at, record_count, source_type, is_demo) "
            "VALUES (?,?,?,?,?)",
            (dataset_id, utcnow(), int(record_count), source_type, int(bool(is_demo))),
        )


def get_dataset(dataset_id: str) -> dict | None:
    with _lock, _connect() as conn:
        row = conn.execute("SELECT * FROM datasets WHERE id = ?", (dataset_id,)).fetchone()
    if not row:
        return None
    return {
        "id": row["id"],
        "record_count": row["record_count"],
        "source_type": row["source_type"],
        "is_demo": bool(row["is_demo"]),
        "created_at": row["created_at"],
    }


def delete_dataset(dataset_id: str) -> bool:
    with _lock, _connect() as conn:
        cur = conn.execute("DELETE FROM datasets WHERE id = ?", (dataset_id,))
    return cur.rowcount > 0


def save_report(report_id: str, run_id: str, fmt: str, filename: str) -> None:
    with _lock, _connect() as conn:
        conn.execute(
            "INSERT INTO reports (id, run_id, format, filename, created_at) VALUES (?,?,?,?,?)",
            (report_id, run_id, fmt, filename, utcnow()),
        )


def list_reports(limit: int = 50) -> list[dict]:
    with _lock, _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM reports ORDER BY created_at DESC LIMIT ?", (limit,)
        ).fetchall()
    return [dict(r) for r in rows]
