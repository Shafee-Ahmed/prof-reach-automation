"""SQLite persistence for outreach candidates and delivery history."""

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from app.core.config import DATABASE_PATH


class OutreachRecord(BaseModel):
    """Persisted candidate and outreach state."""

    candidate_id: str
    name: str
    institution: str
    email: str | None = None
    faculty_url: str | None = None
    relevance_score: float = 0.0
    status: str = "pending"
    subject: str | None = None
    body: str | None = None
    papers: list[dict[str, Any]] = Field(default_factory=list)
    citations: list[dict[str, Any]] = Field(default_factory=list)
    quality_checks: dict[str, Any] = Field(default_factory=dict)
    reviewer_notes: str | None = None
    provider_id: str | None = None
    created_at: str | None = None
    updated_at: str | None = None


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _database_path(path: str | Path | None) -> Path:
    database_path = Path(path or DATABASE_PATH)
    database_path.parent.mkdir(parents=True, exist_ok=True)
    return database_path


def _connect(path: str | Path | None = None) -> sqlite3.Connection:
    connection = sqlite3.connect(_database_path(path))
    connection.row_factory = sqlite3.Row
    return connection


def initialize_database(path: str | Path | None = None) -> None:
    """Create the outreach table and indexes if they do not exist."""
    with _connect(path) as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS outreach (
                candidate_id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                institution TEXT NOT NULL,
                email TEXT,
                faculty_url TEXT,
                relevance_score REAL NOT NULL DEFAULT 0,
                status TEXT NOT NULL,
                subject TEXT,
                body TEXT,
                papers_json TEXT NOT NULL DEFAULT '[]',
                citations_json TEXT NOT NULL DEFAULT '[]',
                quality_checks_json TEXT NOT NULL DEFAULT '{}',
                reviewer_notes TEXT,
                provider_id TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_outreach_status ON outreach(status)"
        )


def _record_from_candidate(candidate: dict[str, Any]) -> OutreachRecord:
    draft = candidate.get("email_draft") or {}
    return OutreachRecord(
        candidate_id=str(candidate["candidate_id"]),
        name=str(candidate.get("name") or candidate.get("professor_name") or ""),
        institution=str(candidate.get("institution") or ""),
        email=candidate.get("email"),
        faculty_url=candidate.get("faculty_url"),
        relevance_score=float(candidate.get("relevance_score") or 0.0),
        status=str(candidate.get("status") or "pending"),
        subject=draft.get("subject"),
        body=draft.get("body"),
        papers=candidate.get("papers") or [],
        citations=draft.get("citations") or [],
        quality_checks=candidate.get("quality_checks") or {},
        reviewer_notes=candidate.get("reviewer_notes"),
    )


def save_candidate(
    candidate: OutreachRecord | dict[str, Any],
    path: str | Path | None = None,
) -> OutreachRecord:
    """Insert or update one candidate while preserving its creation time."""
    record = (
        candidate
        if isinstance(candidate, OutreachRecord)
        else _record_from_candidate(candidate)
    )
    now = _now()
    with _connect(path) as connection:
        initialize_database(path)
        existing = connection.execute(
            "SELECT created_at FROM outreach WHERE candidate_id = ?",
            (record.candidate_id,),
        ).fetchone()
        created_at = (
            str(existing["created_at"]) if existing else record.created_at or now
        )
        updated = record.model_copy(update={"created_at": created_at, "updated_at": now})
        connection.execute(
            """
            INSERT INTO outreach (
                candidate_id, name, institution, email, faculty_url,
                relevance_score, status, subject, body, papers_json,
                citations_json, quality_checks_json, reviewer_notes,
                provider_id, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(candidate_id) DO UPDATE SET
                name=excluded.name,
                institution=excluded.institution,
                email=excluded.email,
                faculty_url=excluded.faculty_url,
                relevance_score=excluded.relevance_score,
                status=excluded.status,
                subject=excluded.subject,
                body=excluded.body,
                papers_json=excluded.papers_json,
                citations_json=excluded.citations_json,
                quality_checks_json=excluded.quality_checks_json,
                reviewer_notes=excluded.reviewer_notes,
                provider_id=excluded.provider_id,
                updated_at=excluded.updated_at
            """,
            (
                updated.candidate_id,
                updated.name,
                updated.institution,
                updated.email,
                updated.faculty_url,
                updated.relevance_score,
                updated.status,
                updated.subject,
                updated.body,
                json.dumps(updated.papers),
                json.dumps(updated.citations),
                json.dumps(updated.quality_checks),
                updated.reviewer_notes,
                updated.provider_id,
                updated.created_at,
                updated.updated_at,
            ),
        )
    return updated


def save_graph_results(
    results: list[dict[str, Any]],
    path: str | Path | None = None,
) -> list[OutreachRecord]:
    """Persist all graph candidates that have stable candidate IDs."""
    records: list[OutreachRecord] = []
    for result in results:
        if result.get("candidate_id"):
            records.append(save_candidate(result, path))
    return records


def _row_to_record(row: sqlite3.Row) -> OutreachRecord:
    return OutreachRecord(
        candidate_id=row["candidate_id"],
        name=row["name"],
        institution=row["institution"],
        email=row["email"],
        faculty_url=row["faculty_url"],
        relevance_score=row["relevance_score"],
        status=row["status"],
        subject=row["subject"],
        body=row["body"],
        papers=json.loads(row["papers_json"]),
        citations=json.loads(row["citations_json"]),
        quality_checks=json.loads(row["quality_checks_json"]),
        reviewer_notes=row["reviewer_notes"],
        provider_id=row["provider_id"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def list_candidates(
    status: str | None = None,
    path: str | Path | None = None,
) -> list[OutreachRecord]:
    """List persisted candidates, optionally filtered by status."""
    initialize_database(path)
    with _connect(path) as connection:
        if status is None:
            rows = connection.execute(
                "SELECT * FROM outreach ORDER BY updated_at DESC"
            ).fetchall()
        else:
            rows = connection.execute(
                "SELECT * FROM outreach WHERE status = ? ORDER BY updated_at DESC",
                (status,),
            ).fetchall()
    return [_row_to_record(row) for row in rows]


def update_candidate_status(
    candidate_id: str,
    status: str,
    reviewer_notes: str | None = None,
    path: str | Path | None = None,
) -> OutreachRecord:
    """Update review status and optional reviewer notes."""
    initialize_database(path)
    with _connect(path) as connection:
        result = connection.execute(
            """
            UPDATE outreach
            SET status = ?, reviewer_notes = ?, updated_at = ?
            WHERE candidate_id = ?
            """,
            (status, reviewer_notes, _now(), candidate_id),
        )
        if result.rowcount != 1:
            raise KeyError(f"Unknown candidate: {candidate_id}")
    return next(
        record
        for record in list_candidates(path=path)
        if record.candidate_id == candidate_id
    )


def record_delivery(
    candidate_id: str,
    status: str,
    provider_id: str | None = None,
    path: str | Path | None = None,
) -> OutreachRecord:
    """Record simulated or real delivery status and provider ID."""
    initialize_database(path)
    with _connect(path) as connection:
        result = connection.execute(
            """
            UPDATE outreach
            SET status = ?, provider_id = ?, updated_at = ?
            WHERE candidate_id = ?
            """,
            (status, provider_id, _now(), candidate_id),
        )
        if result.rowcount != 1:
            raise KeyError(f"Unknown candidate: {candidate_id}")
    return next(
        record
        for record in list_candidates(path=path)
        if record.candidate_id == candidate_id
    )
