# file: app/trace/store.py
"""Audit records: one row per response, full JSON in `record`. No chain-of-thought, PII redacted."""
from __future__ import annotations

import json
import re
import uuid
from datetime import datetime, timezone

from app.data.db import connect

DDL = """CREATE TABLE IF NOT EXISTS traces (
  run_id TEXT PRIMARY KEY, created_utc TEXT NOT NULL, endpoint TEXT, subject_id TEXT,
  answer_type TEXT, latency_ms REAL, llm_calls INTEGER, tokens INTEGER, record TEXT NOT NULL)"""
_PII = [(re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+"), "[email]"),
        (re.compile(r"(?<!\d)(?:\+?91[\s-]?)?[6-9]\d{9}(?!\d)"), "[phone]"),
        (re.compile(r"(?<!\d)\d{12,19}(?!\d)"), "[number]")]


def new_run_id() -> str:
    return uuid.uuid4().hex[:8]


def now_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def redact(text: str) -> str:
    for pattern, token in _PII:
        text = pattern.sub(token, text or "")
    return text


def save_trace(record: dict) -> None:
    conn = connect()
    conn.execute(DDL)
    conn.execute("INSERT OR REPLACE INTO traces VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                 (record["trace_id"], record["timestamp"], record.get("endpoint"), record.get("customer_id"),
                  record.get("answer_type"), record.get("latency_ms"), record.get("llm_calls"),
                  record.get("tokens"), json.dumps(record, default=str)))
    conn.commit()


def get_trace(run_id: str) -> dict | None:
    conn = connect()
    conn.execute(DDL)
    row = conn.execute("SELECT record FROM traces WHERE run_id = ?", (run_id,)).fetchone()
    return json.loads(row[0]) if row else None


def list_traces(limit: int = 200) -> list[dict]:
    conn = connect()
    conn.execute(DDL)
    return [json.loads(r[0]) for r in conn.execute("SELECT record FROM traces ORDER BY created_utc DESC LIMIT ?", (limit,))]
