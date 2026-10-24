# file: app/graph/state.py
from __future__ import annotations

import operator
from typing import Annotated, TypedDict


class GraphState(TypedDict, total=False):
    # inputs: set by the API service, never by the LLM
    run_id: str
    request: dict            # validated request body, e.g. {"question": ..., "as_of_date": ...}
    principal: dict          # identity from headers only, e.g. {"subject_id": "C1001", "role": "customer"}
    # routing
    entities: dict           # {"order_id": ["O-100001"], ...} extracted by regex, not by the LLM
    intent: str
    plan: list[dict]         # [{"tool": "name", "args": {...}}]
    replans: int
    needs_replan: bool
    replan_feedback: str
    # accumulated facts (reducers append, so parallel branches merge safely)
    tool_results: Annotated[list[dict], operator.add]
    evidence: Annotated[list[dict], operator.add]
    rules_applied: Annotated[list[dict], operator.add]
    conflicts: Annotated[list[dict], operator.add]
    assumptions: Annotated[list[str], operator.add]
    flags: Annotated[list[str], operator.add]
    steps: Annotated[list[dict], operator.add]       # the audit trail; never chain-of-thought
    llm_usage: Annotated[list[dict], operator.add]
    # outcome
    refused_reason: str
    clarification: str
    abstain: bool
    answer: str
    explanation: str
    answer_type: str
