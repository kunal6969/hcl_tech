"""
state.py — LangGraph shared State TypedDict.

This is the single data container that flows through every node in the graph.
Each node reads from state and returns a partial dict to update it.
No global variables — all context lives here.
"""
from __future__ import annotations

from typing import Any, TypedDict


class State(TypedDict, total=False):
    """
    Shared state for the Hospital Patient Services graph.

    Fields set by the gateway before graph entry:
      trace_id, patient_id, role, question

    Fields set by each node as the request progresses through the pipeline.
    Using total=False so nodes can return partial updates.
    """

    # --- Set by gateway (trusted, from headers) ---
    trace_id: str          # unique HSP-XXXXX identifier for this request
    patient_id: str        # from X-Patient-Id header; NEVER from question text
    role: str              # "patient" or "admin" from X-Role header
    question: str          # the raw user question

    # --- Set by router ---
    intent: str            # policy_fact | procedure | personal_data | eligibility |
                           # lab_result | drug_check | action_request | out_of_scope | missing_info
    params: dict[str, Any] # extracted params: procedure, test, medications, preferred_date, etc.

    # --- Set by retrieve/tool nodes ---
    chunks: list[dict[str, Any]]       # retrieved policy/procedure chunks from ChromaDB
    tool_results: list[dict[str, Any]] # results from deterministic SQL tools

    # --- Set by build_evidence ---
    evidence: dict[str, Any]           # merged, authoritative evidence packet for composer

    # --- Set by compose / terminal nodes ---
    answer: str
    answer_type: str       # must be one of the 7 answer_types from spec
    citations: list[dict[str, Any]]
    tools_invoked: list[dict[str, Any]]
    explanation: str
    assumptions: list[str]

    # --- Audit metadata (set by audit_writer) ---
    audit: dict[str, Any]  # latency_ms, model, sources, privacy_checks, errors
    start_time: float      # time.monotonic() at graph entry, for latency calculation
