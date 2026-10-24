# file: ui/api_client.py
"""Thin HTTP client for the UI. Every call has a timeout and returns (data, error) instead of raising."""
from __future__ import annotations

import json
import os
from typing import Iterator

import httpx

BASE = os.getenv("API_BASE_URL", "http://localhost:8000")
ASK_PATH = os.getenv("ASK_PATH", "/ask")          # rename to the statement's endpoint
TIMEOUT = float(os.getenv("UI_TIMEOUT", "120"))


def _headers(customer_id: str | None) -> dict:
    return {"X-Customer-Id": customer_id} if customer_id else {}


def get(path: str, customer_id: str | None = None, timeout: float = 10) -> tuple[object | None, str | None]:
    try:
        r = httpx.get(BASE + path, headers=_headers(customer_id), timeout=timeout)
        return (r.json(), None) if r.status_code == 200 else (None, f"{r.status_code}: {r.text[:200]}")
    except httpx.HTTPError as err:
        return None, f"API unreachable at {BASE} ({type(err).__name__})"


def ask(body: dict, customer_id: str | None) -> tuple[dict | None, str | None]:
    try:
        r = httpx.post(BASE + ASK_PATH, json=body, headers=_headers(customer_id), timeout=TIMEOUT)
        return (r.json(), None) if r.status_code == 200 else (None, f"{r.status_code}: {r.text[:300]}")
    except httpx.HTTPError as err:
        return None, f"API unreachable at {BASE} ({type(err).__name__})"


def ask_stream(body: dict, customer_id: str | None) -> Iterator[dict]:
    """Yields SSE events from /ask/stream; raises httpx errors so the caller can fall back to ask()."""
    with httpx.stream("POST", BASE + ASK_PATH + "/stream", json=body, headers=_headers(customer_id),
                      timeout=TIMEOUT) as r:
        r.raise_for_status()
        for line in r.iter_lines():
            if line.startswith("data: "):
                yield json.loads(line[6:])


def ingest(file_name: str, data: bytes, metadata: dict) -> tuple[dict | None, str | None]:
    try:
        r = httpx.post(BASE + "/ingest", files={"file": (file_name, data)},
                       data={"metadata": json.dumps(metadata)}, timeout=TIMEOUT)
        return (r.json(), None) if r.status_code == 200 else (None, f"{r.status_code}: {r.text[:300]}")
    except httpx.HTTPError as err:
        return None, f"API unreachable at {BASE} ({type(err).__name__})"
