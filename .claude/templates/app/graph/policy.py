# file: app/graph/policy.py
"""Problem-specific routing and answer policy. Every value comes from docs/REQUIREMENTS.md.
Generic node code in app/graph/nodes.py reads these names: change values here, not node code."""
from __future__ import annotations

from typing import Any

# --- answer types: copy the statement's table verbatim ------------------------------------
REFUSED = "refused"
CLARIFY = "clarification_needed"
CONFLICT: str | None = "conflict_flagged"      # None if the statement has no such type
ABSTAIN = "not_found"                          # e.g. "not_in_data" for analytics briefs
TOOL_RESULT = "calculated"
RETRIEVED = "retrieved_fact"
INTENT_ANSWER_TYPE: dict[str, str] = {}        # e.g. {"bill_bridge": "decomposition", "plan": "recommendation"}

# --- fixed messages: verbatim where the statement gives one -------------------------------
NOT_FOUND_MESSAGE = "I could not find this information in the authorised sources."
CLARIFY_DEFAULT = "Could you tell me which item, order or period you mean?"
CLARIFY_EMPTY = "Please type a question."
INJECTION_NOTE = "Instruction-like text in the request was treated as data and ignored."


def refusal_message(state: dict) -> str:
    reasons = [state.get("refused_reason", "")] + [
        (s.get("output") or {}).get("error", "") for s in state.get("steps", []) if s.get("status") == "refused"]
    if "identity_required" in reasons:
        return "Please sign in so I can look up your own records."
    # identical wording whether the record exists or not: never reveal other users' data
    return "I can only help with records on your own account, and I can't find that one there."


# --- entities: identifier formats from the data schema (no capture groups) ----------------
ENTITY_PATTERNS: dict[str, str] = {
    # "order_id": r"\bO-\d{6}\b",
    # "customer_id": r"\bC\d{4}\b",
}
PRINCIPAL_ENTITY = "customer_id"   # an entity of this type must equal principal.subject_id

# --- deterministic routing rules: checked in order before any LLM call --------------------
INTENT_RULES: list[dict[str, Any]] = [
    # {"intent": "order_status", "pattern": r"\b(where|status|track)\b.*\border\b",
    #  "requires": ["order_id"], "plan": [{"tool": "lookup_order", "args": {"order_id": "{order_id}"}}]},
]
INTENTS: list[str] = []                        # every intent the planner may choose
OUT_OF_SCOPE_PATTERNS: list[str] = []          # e.g. r"\bnext year\b", r"\bforecast\b"
INJECTION_PATTERNS: dict[str, str] = {
    "override": r"\b(ignore|disregard|forget)\b.{0,40}\b(instructions|rules|policy|above)\b",
    "role_play": r"\b(you are now|act as|pretend to be|system prompt)\b",
    "forced_action": r"\b(approve|issue|process|grant)\b.{0,30}\b(refund|payment|return|discount)\b",
}
RETRIEVAL_TOOLS: set[str] = {"search_documents"}


def fallback_plan(question: str) -> list[dict]:
    """Plan used when no rule matched and the LLM is unavailable (MOCK or outage).
    Retrieval-first problems: [{"tool": "search_documents", "args": {"query": question}}]."""
    return []


def decide_answer_type(state: dict) -> str:
    steps = state.get("steps", [])
    if state.get("refused_reason") or any(s.get("status") == "refused" for s in steps):
        return REFUSED
    if state.get("clarification"):
        return CLARIFY
    if CONFLICT and any(c.get("unresolved") for c in state.get("conflicts", [])):
        return CONFLICT
    if state.get("abstain"):
        return ABSTAIN
    if state.get("intent") in INTENT_ANSWER_TYPE:
        return INTENT_ANSWER_TYPE[state["intent"]]
    current = [r for r in state.get("tool_results", []) if r.get("attempt", 0) == state.get("replans", 0)]
    if any(r["status"] == "ok" and r["tool"] not in RETRIEVAL_TOOLS for r in current):
        return TOOL_RESULT
    if state.get("evidence"):
        return RETRIEVED
    return ABSTAIN


def template_synthesis(state: dict, facts: dict):
    """Deterministic answer for MOCK_LLM, provider outages and guard failures.
    It only restates FACTS, so it always passes the faithfulness guard. Write per-intent
    templates in S4 for nicer wording; keep this generic one as the last resort."""
    from app.graph.nodes import Synthesis
    lines: list[str] = []
    ordered = sorted(facts.get("tool_results", []), key=lambda r: r.get("tool") in RETRIEVAL_TOOLS)
    for r in ordered:  # computed results first, retrieval stats last
        out = r.get("output")
        if r.get("status") == "ok" and isinstance(out, dict):
            flat = {k: v for k, v in out.items() if not isinstance(v, (list, dict))}
            if flat:
                lines.append(f"{r['tool']}: " + "; ".join(f"{k} = {v}" for k, v in flat.items()))
    for e in facts.get("evidence", [])[:2]:
        lines.append(f"[{e.get('doc_id')} {e.get('section') or ''}] {str(e.get('text', ''))[:240]}")
    if not lines:
        return Synthesis(answer=NOT_FOUND_MESSAGE, supported=False)
    return Synthesis(answer=lines[0], explanation="\n".join(lines[1:]), supported=True)
