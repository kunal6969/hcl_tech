"""
schemas.py — Pydantic v2 contract models, transcribed verbatim from the statement.

Every field name, type and enum value here matches the spec exactly.
The output_guard node also validates against these models before returning.
"""
from __future__ import annotations

from typing import Any
from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# answer_type enum — verbatim from spec section 6
# ---------------------------------------------------------------------------
ANSWER_TYPES = {
    "retrieved_fact",       # fact supported directly by approved documents
    "calculated",           # result produced by a deterministic tool
    "action_completed",     # authorized workflow executed successfully
    "clarification_needed", # required information is missing or ambiguous
    "not_found",            # authorized sources do not contain the answer
    "refused",              # request is unauthorized or unsafe
    "conflict_flagged",     # policies conflict and cannot be resolved automatically
}

# Verbatim not-found message from the statement (section 3)
NOT_FOUND_MSG = "I could not find this information in the authorised hospital sources."


# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------

class ChatRequest(BaseModel):
    """Body for POST /chat."""
    question: str = Field(..., description="The patient's question or action request")
    confirm: bool = Field(
        default=False,
        description="Set true to confirm a pending action (e.g., reschedule). Not used in MVP one-step flow."
    )


class IngestRequest(BaseModel):
    """Metadata form fields for POST /admin/ingest (multipart)."""
    authority: str = Field(
        default="hospital_policy",
        description="Document authority level: 'government_regulation' | 'clinical_guideline' | 'hospital_policy'"
    )
    version: str = Field(default="1.0", description="Document version string, e.g. '2.1'")
    effective_date: str = Field(
        ...,
        description="ISO date when this document becomes effective, e.g. '2026-01-01'"
    )
    section: str = Field(default="General", description="Section or chapter name within the document")


# ---------------------------------------------------------------------------
# Citation model
# ---------------------------------------------------------------------------

class Citation(BaseModel):
    """One citation entry in a response — points to the source that supports the answer."""
    system: str | None = Field(None, description="Operational system name, e.g. 'Hospital Scheduling System'")
    doc: str | None = Field(None, description="Document file name or title")
    section: str | None = Field(None, description="Section within the document")
    version: str | None = Field(None, description="Document version")
    effective_date: str | None = Field(None, description="Document effective date")


# ---------------------------------------------------------------------------
# Tool invocation record
# ---------------------------------------------------------------------------

class ToolInvoked(BaseModel):
    """Records a single deterministic tool call in the trace."""
    tool: str = Field(..., description="Tool function name, e.g. 'get_appointments'")
    params: dict[str, Any] = Field(default_factory=dict, description="Parameters passed (patient_id masked in logs)")
    result_summary: str | None = Field(None, description="One-line summary of the result")


# ---------------------------------------------------------------------------
# Main response model — verbatim from spec section 8
# ---------------------------------------------------------------------------

class ChatResponse(BaseModel):
    """
    Response from POST /chat.

    Verbatim from spec:
    {
      "trace_id": "HSP-93214",
      "answer": "Your MRI appointment is scheduled for 14 Oct 2026 at 10:30 AM.",
      "answer_type": "calculated",
      "citations": [{"system": "Hospital Scheduling System"}],
      "tools_invoked": [{"tool": "get_appointments"}],
      "explanation": "Retrieved from the patient appointment management system."
    }
    """
    trace_id: str = Field(..., description="Unique trace ID for this request, e.g. 'HSP-93214'")
    answer: str = Field(..., description="The assistant's response to the patient")
    answer_type: str = Field(..., description="One of the 7 answer_type values from spec section 6")
    citations: list[Citation] = Field(default_factory=list, description="Sources supporting the answer")
    tools_invoked: list[ToolInvoked] = Field(default_factory=list, description="Deterministic tools used")
    explanation: str = Field(default="", description="How the answer was produced")
    assumptions: list[str] = Field(default_factory=list, description="Assumptions made by the system")


# ---------------------------------------------------------------------------
# Health check response
# ---------------------------------------------------------------------------

class HealthResponse(BaseModel):
    """Response from GET /health."""
    status: str = Field(default="ok")
    sqlite: str = Field(default="unknown")
    chromadb: str = Field(default="unknown")
    llm_mock: bool = Field(default=False)


# ---------------------------------------------------------------------------
# Ingest response
# ---------------------------------------------------------------------------

class IngestResponse(BaseModel):
    """Response from POST /admin/ingest."""
    status: str = Field(default="ok", description="'ok' or 'error'")
    doc_id: str = Field(default="", description="ChromaDB document ID assigned")
    chunks_added: int = Field(default=0, description="Number of text chunks indexed")
    message: str = Field(default="", description="Human-readable summary")
