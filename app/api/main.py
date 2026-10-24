"""
main.py — FastAPI application entry point for the Hospital Patient Services Assistant.

Endpoints (R10, R11):
  POST /chat              — Ask a question or request an action
  POST /admin/ingest      — Upload a new hospital document (admin only)
  GET  /trace/{trace_id}  — Retrieve audit trace for a request
  GET  /health            — Health check (SQLite + ChromaDB + LLM mode)

Identity is set from headers only (R7):
  X-Patient-Id: P1001
  X-Role: patient | admin

The graph is imported from app.graph.build and invoked per request.
All errors return a valid ChatResponse (never a bare 500).
"""
from __future__ import annotations

import os
import time
import uuid
from pathlib import Path

# Load .env before any other app imports so API keys are available
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parents[2] / ".env", override=True)
except ImportError:
    pass  # python-dotenv optional; keys can be set in the shell environment

from fastapi import FastAPI, Header, HTTPException, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware

from app.api.schemas import (
    ChatRequest,
    ChatResponse,
    Citation,
    HealthResponse,
    IngestResponse,
    NOT_FOUND_MSG,
    ToolInvoked,
)

# Build the graph once on startup
from app.graph.build import hospital_graph

app = FastAPI(
    title="Hospital Patient Services Assistant",
    description="AI-powered assistant for hospital patient services. Grounded, secure, auditable.",
    version="1.0.0",
)

# Allow Streamlit UI to call from localhost
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# POST /chat — main endpoint
# ---------------------------------------------------------------------------

@app.post("/chat", response_model=ChatResponse)
async def chat(
    body: ChatRequest,
    x_patient_id: str = Header(..., alias="X-Patient-Id", description="Patient ID from auth context"),
    x_role: str = Header(default="patient", alias="X-Role", description="User role: patient or admin"),
) -> ChatResponse:
    """
    Handle a patient's question or action request.

    Identity comes from X-Patient-Id header ONLY — never from the question text.
    The graph handles all routing, tools, safety checks, and audit logging.
    """
    trace_id = f"HSP-{uuid.uuid4().hex[:8].upper()}"

    # Initialize graph state
    initial_state = {
        "trace_id": trace_id,
        "patient_id": x_patient_id,
        "role": x_role,
        "question": body.question,
        "start_time": time.monotonic(),
        "intent": "",
        "params": {},
        "chunks": [],
        "tool_results": [],
        "evidence": {},
        "answer": "",
        "answer_type": "",
        "citations": [],
        "tools_invoked": [],
        "explanation": "",
        "assumptions": [],
        "audit": {},
    }

    try:
        # Run the full graph
        final_state = hospital_graph.invoke(initial_state)
    except Exception as exc:
        # Never return a bare 500 — return a valid refused response
        return ChatResponse(
            trace_id=trace_id,
            answer="An internal error occurred. Please try again later.",
            answer_type="refused",
            citations=[],
            tools_invoked=[],
            explanation=f"System error: {type(exc).__name__}",
            assumptions=[],
        )

    # Build the response from the final state
    citations = [
        Citation(**c) if isinstance(c, dict) else c
        for c in (final_state.get("citations") or [])
    ]
    tools_invoked = [
        ToolInvoked(**t) if isinstance(t, dict) else t
        for t in (final_state.get("tools_invoked") or [])
    ]

    return ChatResponse(
        trace_id=trace_id,
        answer=final_state.get("answer") or NOT_FOUND_MSG,
        answer_type=final_state.get("answer_type") or "not_found",
        citations=citations,
        tools_invoked=tools_invoked,
        explanation=final_state.get("explanation") or "",
        assumptions=final_state.get("assumptions") or [],
    )


# ---------------------------------------------------------------------------
# POST /admin/ingest — live document ingestion (R11)
# ---------------------------------------------------------------------------

@app.post("/admin/ingest", response_model=IngestResponse)
async def admin_ingest(
    file: UploadFile = File(..., description="PDF, Markdown, or TXT document to ingest"),
    authority: str = Form(default="hospital_policy"),
    version: str = Form(default="1.0"),
    effective_date: str = Form(..., description="ISO date, e.g. 2026-01-01"),
    section: str = Form(default="General"),
    x_role: str = Header(default="patient", alias="X-Role"),
) -> IngestResponse:
    """
    Upload and index a new hospital document without restarting (R11).

    Only admin role can ingest documents. The document is immediately searchable.
    Supported formats: PDF, Markdown (.md), plain text (.txt).
    """
    # Authorization: admin role required
    if x_role != "admin":
        raise HTTPException(status_code=403, detail="Admin role required for document ingestion")

    # Save uploaded file to a temp location
    import tempfile
    suffix = Path(file.filename or "doc.txt").suffix.lower()
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        content = await file.read()
        tmp.write(content)
        tmp_path = tmp.name

    try:
        from app.rag.ingest_docs import ingest_document
        result = ingest_document(
            file_path=Path(tmp_path),
            doc_name=file.filename or "uploaded_doc",
            authority=authority,
            version=version,
            effective_date=effective_date,
            section=section,
        )
    finally:
        os.unlink(tmp_path)  # clean up temp file

    return IngestResponse(
        status="ok" if result.get("success") else "error",
        doc_id=result.get("doc_id", ""),
        chunks_added=result.get("chunks_added", 0),
        message=result.get("message", ""),
    )


# ---------------------------------------------------------------------------
# GET /trace/{trace_id} — audit trace retrieval (R10)
# ---------------------------------------------------------------------------

@app.get("/trace/{trace_id}")
async def get_trace(
    trace_id: str,
    x_patient_id: str = Header(..., alias="X-Patient-Id"),
) -> dict:
    """
    Retrieve the audit trace for a previous request.

    Only the patient who made the request can retrieve its trace (R7).
    """
    from app.trace.store import get_trace as fetch_trace

    trace = fetch_trace(trace_id, x_patient_id)
    if not trace:
        raise HTTPException(
            status_code=404,
            detail="Trace not found or not authorized for your account",
        )
    return trace


# ---------------------------------------------------------------------------
# GET /health — system health check
# ---------------------------------------------------------------------------

@app.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    """
    Check system health: SQLite DB, ChromaDB, and LLM mode.
    Used by the Docker healthcheck and the Streamlit UI.
    """
    # Check SQLite
    sqlite_status = "ok"
    try:
        from app.trace.store import _DB_PATH
        if not _DB_PATH.exists():
            sqlite_status = "db_not_found"
        else:
            import sqlite3
            sqlite3.connect(str(_DB_PATH)).execute("SELECT 1").fetchone()
    except Exception as e:
        sqlite_status = f"error: {e}"

    # Check ChromaDB
    chroma_status = "ok"
    try:
        from app.rag.index import _get_collection
        col = _get_collection()
        col.count()  # just count docs; no query needed
    except Exception as e:
        chroma_status = f"error: {e}"

    return HealthResponse(
        status="ok",
        sqlite=sqlite_status,
        chromadb=chroma_status,
        llm_mock=os.getenv("MOCK_LLM", "false").lower() in ("1", "true", "yes"),
    )
