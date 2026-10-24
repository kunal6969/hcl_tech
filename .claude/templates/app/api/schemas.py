# file: app/api/schemas.py
"""API contract. Field names, nesting and enum values are copied VERBATIM from the problem statement."""
from __future__ import annotations

from datetime import date
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

AnswerType = Literal["retrieved_fact", "calculated", "not_found", "clarification_needed", "refused",
                     "conflict_flagged"]                                    # ← the statement's table


class AskRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")
    question: str = Field(default="", max_length=4000)
    as_of_date: date | None = None


class Citation(BaseModel):
    doc_id: str
    title: str = ""
    section: str = ""
    page: int | None = None
    version: str = ""
    effective_from: str = ""


class ToolInvocation(BaseModel):
    tool: str
    input: dict[str, Any] = Field(default_factory=dict)
    output: Any = None


class AppliedRule(BaseModel):
    rule_id: str
    value: Any = None
    source_doc_id: str = ""


class Conflict(BaseModel):
    model_config = ConfigDict(extra="allow")
    parameter: str = ""
    winner: str | None = None
    resolution: list[str] = Field(default_factory=list)


class AskResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    trace_id: str
    answer: str
    answer_type: AnswerType
    citations: list[Citation] = Field(default_factory=list)
    tools_invoked: list[ToolInvocation] = Field(default_factory=list)
    applied_rules: list[AppliedRule] = Field(default_factory=list)
    conflicts_detected: list[Conflict] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    explanation: str = ""
    as_of_date: str


class IngestResponse(BaseModel):
    model_config = ConfigDict(extra="allow")
    status: str
    doc_id: str | None = None
    chunks_indexed: int | None = None
    table: str | None = None
    rows_loaded: int | None = None
    rows_rejected: int | None = None
