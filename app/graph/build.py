"""
build.py — Wire the LangGraph StateGraph with all nodes and conditional edges.

The graph is a Tier 1 fixed graph: all routes are determined at design time.
No dynamic planner or supervisor needed (see docs/ARCHITECTURE.md).

Entry: START → input_guard
Exit: Every path reaches audit_writer → END

Conditional routing happens at three decision points:
  1. After input_guard: refused → audit; safe → router
  2. After router: intent determines which node to call next
  3. After resolve: resolved / not_found / conflict_flagged
"""
from __future__ import annotations

from langgraph.graph import StateGraph, END

from app.graph.state import State
from app.graph.nodes import (
    input_guard,
    router,
    retrieve,
    resolve,
    tool_executor,
    action_workflow,
    build_evidence,
    compose,
    output_guard,
    audit_writer,
)
from app.graph.policy import (
    INTENT_ACTION,
    INTENT_DRUG_CHECK,
    INTENT_ELIGIBILITY,
    INTENT_LAB_RESULT,
    INTENT_MISSING_INFO,
    INTENT_OUT_OF_SCOPE,
    INTENT_PERSONAL_DATA,
    INTENT_POLICY_FACT,
    INTENT_PROCEDURE,
)


# ---------------------------------------------------------------------------
# Routing functions (called by add_conditional_edges)
# ---------------------------------------------------------------------------

def _after_input_guard(state: State) -> str:
    """
    If input_guard set answer_type='refused', skip straight to audit.
    Otherwise proceed to router.
    """
    if state.get("answer_type") == "refused":
        return "audit_writer"
    return "router"


def _after_router(state: State) -> str:
    """
    Route to the appropriate node based on the intent classified by router.
    """
    intent = state.get("intent", "")
    # Terminal: missing info or out of scope
    if intent in (INTENT_MISSING_INFO, INTENT_OUT_OF_SCOPE):
        return "handle_terminal"
    # Knowledge path
    if intent in (INTENT_POLICY_FACT, INTENT_PROCEDURE):
        return "retrieve"
    # Tool path
    if intent in (INTENT_PERSONAL_DATA, INTENT_ELIGIBILITY, INTENT_LAB_RESULT, INTENT_DRUG_CHECK):
        return "tool_executor"
    # Action path
    if intent == INTENT_ACTION:
        return "action_workflow"
    # Fallback
    return "handle_terminal"


def _after_resolve(state: State) -> str:
    """
    After resolve:
    - If a terminal answer_type was set (not_found, conflict_flagged) → audit
    - Otherwise → build_evidence
    """
    at = state.get("answer_type")
    if at in ("not_found", "conflict_flagged"):
        return "audit_writer"
    return "build_evidence"


def _after_tool_or_action(state: State) -> str:
    """
    After tool_executor or action_workflow:
    - If a terminal answer was set (refused, clarification_needed) → audit
    - Otherwise → build_evidence
    """
    at = state.get("answer_type")
    if at in ("refused", "clarification_needed"):
        return "audit_writer"
    return "build_evidence"


def _after_output_guard(state: State) -> str:
    """Always proceed to audit after output guard."""
    return "audit_writer"


# ---------------------------------------------------------------------------
# Terminal handler for out_of_scope and missing_info
# ---------------------------------------------------------------------------

def handle_terminal(state: State) -> dict:
    """
    Terminal node for out_of_scope and missing_info intents.
    Sets not_found or clarification_needed as appropriate.
    """
    intent = state.get("intent", "")
    if intent == INTENT_MISSING_INFO:
        return {
            "answer": "I need more information to answer your question. Could you provide more details?",
            "answer_type": "clarification_needed",
            "citations": [],
            "tools_invoked": [],
            "explanation": "Insufficient information to process the request.",
            "assumptions": [],
        }
    # out_of_scope and anything else
    return {
        "answer": "I could not find this information in the authorised hospital sources.",
        "answer_type": "not_found",
        "citations": [],
        "tools_invoked": [],
        "explanation": "Request is outside the scope of hospital services.",
        "assumptions": [],
    }


# ---------------------------------------------------------------------------
# Build and compile the graph
# ---------------------------------------------------------------------------

def build_graph():
    """
    Build and compile the Hospital Patient Services LangGraph.

    Returns a compiled graph that can be invoked with:
        graph.invoke({"question": "...", "patient_id": "P1001", ...})
    """
    g = StateGraph(State)

    # --- Register all nodes ---
    g.add_node("input_guard", input_guard)
    g.add_node("router", router)
    g.add_node("retrieve", retrieve)
    g.add_node("resolve", resolve)
    g.add_node("tool_executor", tool_executor)
    g.add_node("action_workflow", action_workflow)
    g.add_node("handle_terminal", handle_terminal)
    g.add_node("build_evidence", build_evidence)
    g.add_node("compose", compose)
    g.add_node("output_guard", output_guard)
    g.add_node("audit_writer", audit_writer)

    # --- Set entry point ---
    g.set_entry_point("input_guard")

    # --- Conditional edges ---
    g.add_conditional_edges(
        "input_guard",
        _after_input_guard,
        {"audit_writer": "audit_writer", "router": "router"},
    )
    g.add_conditional_edges(
        "router",
        _after_router,
        {
            "retrieve": "retrieve",
            "tool_executor": "tool_executor",
            "action_workflow": "action_workflow",
            "handle_terminal": "handle_terminal",
        },
    )
    g.add_conditional_edges(
        "resolve",
        _after_resolve,
        {"audit_writer": "audit_writer", "build_evidence": "build_evidence"},
    )
    g.add_conditional_edges(
        "tool_executor",
        _after_tool_or_action,
        {"audit_writer": "audit_writer", "build_evidence": "build_evidence"},
    )
    g.add_conditional_edges(
        "action_workflow",
        _after_tool_or_action,
        {"audit_writer": "audit_writer", "build_evidence": "build_evidence"},
    )

    # --- Linear edges ---
    g.add_edge("retrieve", "resolve")
    g.add_edge("handle_terminal", "audit_writer")
    g.add_edge("build_evidence", "compose")
    g.add_edge("compose", "output_guard")
    g.add_edge("output_guard", "audit_writer")
    g.add_edge("audit_writer", END)

    return g.compile()


# Singleton: compile once on import
hospital_graph = build_graph()
