# file: app/api/main.py
from __future__ import annotations

import json
import os
import re
import tempfile
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from starlette.concurrency import run_in_threadpool

from app.api.schemas import AskRequest, AskResponse, IngestResponse
from app.api.service import answer, stream_answer
from app.data.db import connect, data_dir, data_version
from app.llm.gateway import get_gateway
from app.trace.store import get_trace

META_KEYS = {"metadata", "meta", "json", "config", "source", "source_register"}
TABLE_SUFFIXES = {".csv", ".tsv", ".xlsx", ".xls", ".parquet"}
PRINCIPAL_RE = re.compile(os.getenv("PRINCIPAL_PATTERN", r"^[A-Za-z0-9_-]{1,64}$"))


@asynccontextmanager
async def lifespan(_: FastAPI):
    import app.data.tables  # noqa: F401  register TableSpecs
    import app.tools.catalog  # noqa: F401  register tools
    connect()
    (data_dir() / "docs").mkdir(parents=True, exist_ok=True)
    yield


app = FastAPI(title=os.getenv("APP_TITLE", "Hackathon AI Service"), version="1.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


def principal_from(customer_id: str | None) -> dict:
    if customer_id and PRINCIPAL_RE.match(customer_id.strip()):
        return {"subject_id": customer_id.strip().upper(), "role": "customer"}
    return {}


@app.post("/ask", response_model=AskResponse)            # ← rename to the statement's path (e.g. /analyze)
def ask(body: AskRequest, x_customer_id: str | None = Header(default=None, alias="X-Customer-Id")):
    response, _ = answer(body, principal_from(x_customer_id))
    return response


@app.post("/ask/stream")
def ask_stream(body: AskRequest, x_customer_id: str | None = Header(default=None, alias="X-Customer-Id")):
    def events():
        for event in stream_answer(body, principal_from(x_customer_id)):
            yield f"data: {json.dumps(event, default=str)}\n\n"
    return StreamingResponse(events(), media_type="text/event-stream")


async def _parse_multipart(request: Request) -> tuple[tuple[str, bytes] | None, dict]:
    form = await request.form()
    data_file, meta = None, {}
    for key, value in form.multi_items():
        if hasattr(value, "filename") and hasattr(value, "read"):
            raw = await value.read()
            name = value.filename or key
            is_json = name.lower().endswith(".json") or "json" in (value.content_type or "")
            if is_json and (key.lower() in META_KEYS or data_file is not None or key.lower() != "file"):
                meta.update(json.loads(raw.decode("utf-8-sig") or "{}"))
            elif data_file is None:
                data_file = (name, raw)
        else:
            text = str(value).strip()
            if key.lower() in META_KEYS or text.startswith("{"):
                try:
                    meta.update(json.loads(text))
                    continue
                except json.JSONDecodeError:
                    pass
            meta[key] = text
    return data_file, meta


@app.post("/ingest", response_model=IngestResponse, response_model_exclude_none=True)
async def ingest(request: Request):
    from app.data.ingest import ingest_table
    from app.rag.ingest_docs import ingest_document
    data_file, meta = await _parse_multipart(request)
    if data_file is None:
        raise HTTPException(422, "multipart upload must include a file")
    name, raw = data_file
    safe = re.sub(r"[^A-Za-z0-9._-]+", "_", Path(name).name)
    suffix = Path(safe).suffix.lower()
    if meta.get("table") or suffix in TABLE_SUFFIXES:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / safe
            path.write_bytes(raw)
            res = await run_in_threadpool(ingest_table, path, meta.get("table"), meta.get("mode", "upsert"), safe)
        return {k: v for k, v in res.items() if k != "checks"}
    rules = meta.pop("rules", None)
    doc_id = str(meta.get("doc_id") or Path(safe).stem).upper()
    meta["doc_id"] = doc_id
    path = data_dir() / "docs" / f"{doc_id}{suffix}"        # keep originals: judges open the cited page
    path.write_bytes(raw)
    return await run_in_threadpool(ingest_document, path, meta, rules)


@app.get("/health")
def health():
    checks: dict = {"api": "ok"}
    try:
        checks["sqlite"] = "ok" if connect().execute("SELECT 1").fetchone() else "error"
        checks["data_version"] = data_version(connect())
    except Exception as err:
        checks["sqlite"] = f"error: {err}"
    try:
        from app.rag.index import get_index
        checks["vector_store"] = f"ok ({get_index().count()} chunks)"
    except Exception as err:
        checks["vector_store"] = f"error: {type(err).__name__}"
    checks["llm"] = get_gateway().health()
    healthy = checks["sqlite"] == "ok" and checks["vector_store"].startswith("ok") and checks["llm"]["status"] == "ok"
    checks["status"] = "ok" if healthy else "degraded"
    return checks


def _authorised(record: dict, customer_id: str | None, admin_token: str | None) -> bool:
    admin = os.getenv("ADMIN_TOKEN")
    if admin and admin_token == admin:
        return True
    owner = record.get("customer_id")
    return owner is None or (customer_id or "").strip().upper() == owner


@app.get("/audit/{trace_id}")
@app.get("/trace/{trace_id}")
def audit(trace_id: str, x_customer_id: str | None = Header(default=None, alias="X-Customer-Id"),
          x_admin_token: str | None = Header(default=None, alias="X-Admin-Token")):
    record = get_trace(trace_id)
    if record is None or not _authorised(record, x_customer_id, x_admin_token):
        raise HTTPException(404, "trace not found")             # same answer for 'not yours' and 'missing'
    return record


@app.get("/sources")
def sources():
    cur = connect().execute("SELECT * FROM source_register ORDER BY authority_level, effective_from")
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, r, strict=True)) for r in cur.fetchall()]


@app.get("/documents/{doc_id}")
def document(doc_id: str):
    matches = sorted((data_dir() / "docs").glob(f"{re.sub(r'[^A-Za-z0-9._-]', '', doc_id).upper()}.*"))
    if not matches:
        raise HTTPException(404, "document not found")
    return FileResponse(matches[0])


@app.post("/admin/load")
def admin_load(payload: dict, x_admin_token: str | None = Header(default=None, alias="X-Admin-Token")):
    """HTTP twin of scripts/load_data.py for judges who prefer an endpoint."""
    if not os.getenv("ADMIN_TOKEN") or x_admin_token != os.getenv("ADMIN_TOKEN"):
        raise HTTPException(403, "admin token required")
    from app.data.ingest import ingest_table
    from app.data.validate import infer_table
    folder = Path(payload.get("dir", ""))
    return [ingest_table(p, mode=payload.get("mode", "upsert")) for p in sorted(folder.glob("*"))
            if p.suffix.lower() in TABLE_SUFFIXES and infer_table(p.name)]
