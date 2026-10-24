"""
store.py — Audit trace storage for the Hospital assistant (R10).

Every request generates a trace_id and is logged to the audit_log table.
PII (patient_id, question text) is partially redacted before storage.

Functions:
  write_audit()  — called by audit_writer node
  get_trace()    — called by GET /trace/{trace_id}
"""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_DB_PATH = Path(__file__).parents[2] / "data" / "hospital.db"


def _conn() -> sqlite3.Connection:
    """Open a connection to the hospital database."""
    conn = sqlite3.connect(str(_DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def write_audit(
    trace_id: str,
    patient_id: str,
    question_redacted: str,
    answer_type: str,
    tools_used: str,
    latency_ms: float,
    model: str,
    error: str | None,
) -> None:
    """
    Write an audit log entry for a completed request.

    patient_id is stored as masked form (P**** instead of actual ID).
    question_redacted should have PII removed by the caller (nodes.py:audit_writer).
    """
    # Mask patient_id to last 4 digits only
    masked_id = f"P****{patient_id[-4:]}" if len(patient_id) >= 4 else "P****"
    created_at = datetime.now(timezone.utc).isoformat()

    with _conn() as conn:
        conn.execute(
            """
            INSERT INTO audit_log
              (trace_id, patient_id, question_redacted, answer_type,
               tools_used, latency_ms, model, error, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (trace_id, masked_id, question_redacted, answer_type,
             tools_used, latency_ms, model, error, created_at),
        )
        conn.commit()


def get_trace(trace_id: str, requesting_patient_id: str) -> dict[str, Any] | None:
    """
    Retrieve a trace by trace_id for the requesting patient only (R7).

    Returns None if the trace doesn't exist or belongs to a different patient.
    Note: we compare masked IDs so even in the DB we can't leak cross-patient info.
    """
    masked_id = f"P****{requesting_patient_id[-4:]}" if len(requesting_patient_id) >= 4 else "P****"

    with _conn() as conn:
        row = conn.execute(
            """
            SELECT trace_id, patient_id, question_redacted, answer_type,
                   tools_used, latency_ms, model, error, created_at
            FROM audit_log
            WHERE trace_id = ? AND patient_id = ?
            """,
            (trace_id, masked_id),
        ).fetchone()

    return dict(row) if row else None
