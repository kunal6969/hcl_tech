# file: app/api/service.py
from __future__ import annotations

import time
from datetime import date

from langgraph.errors import GraphRecursionError

from app.api.schemas import AskRequest, AskResponse
from app.data.db import connect, data_version
from app.graph import policy
from app.graph.build import get_graph, run_graph
from app.trace.store import new_run_id, now_utc, redact, save_trace

TOOL_NODES = {"execute", "retrieval_agent", "analytics_agent", "action_agent"}


def _dedupe(items: list, key) -> list:
    seen, out = set(), []
    for it in items:
        k = key(it)
        if k not in seen:
            seen.add(k)
            out.append(it)
    return out


def build_response(run_id: str, state: dict, as_of: str) -> dict:
    """Map graph state to the contract. Edit field mapping here when the statement's JSON differs."""
    answer_type = state.get("answer_type") or policy.ABSTAIN
    grounded = answer_type not in {policy.REFUSED, policy.CLARIFY, policy.ABSTAIN}
    tool_steps = [s for s in state.get("steps", []) if s.get("node") in TOOL_NODES and s.get("tool")]
    citations = []
    if grounded:
        citations = [{"doc_id": e.get("doc_id", ""), "title": e.get("title", ""), "section": str(e.get("section") or ""),
                      "page": e.get("page"), "version": str(e.get("version") or ""),
                      "effective_from": str(e.get("effective_from") or "")} for e in state.get("evidence", [])]
        citations += [{"doc_id": r.get("source_doc_id", ""), "title": r.get("title", ""),
                       "section": str(r.get("source_section") or ""), "version": str(r.get("version") or ""),
                       "effective_from": str(r.get("effective_from") or "")} for r in state.get("rules_applied", [])]
    body = {
        "trace_id": run_id,
        "answer": state.get("answer") or policy.NOT_FOUND_MESSAGE,
        "answer_type": answer_type,
        "citations": _dedupe(citations, lambda c: (c["doc_id"], c["section"]))[:8],
        "tools_invoked": [{"tool": s["tool"], "input": s.get("input") or {}, "output": s.get("output")}
                          for s in tool_steps if s.get("status") != "refused"] if grounded else [],
        "applied_rules": _dedupe([{"rule_id": r["rule_id"], "value": r.get("value"),
                                   "source_doc_id": r.get("source_doc_id", "")} for r in state.get("rules_applied", [])],
                                 lambda r: r["rule_id"]),
        "conflicts_detected": state.get("conflicts", []) if grounded or answer_type == policy.CONFLICT else [],
        "assumptions": list(dict.fromkeys(state.get("assumptions", []))),
        "explanation": state.get("explanation", "") if grounded else "",
        "as_of_date": as_of,
    }
    return AskResponse.model_validate(body).model_dump(mode="json")


def build_audit(run_id: str, state: dict, response: dict, request: dict, principal: dict,
                latency_ms: float, endpoint: str) -> dict:
    usage = state.get("llm_usage", [])
    tool_steps = [s for s in state.get("steps", []) if s.get("tool") and s.get("tool") != "llm"]
    decisions = [d for s in tool_steps if isinstance(s.get("output"), dict)
                 for d in s["output"].get("precedence_decisions", [])]
    try:
        version = data_version(connect())
    except Exception:
        version = None
    return {
        "trace_id": run_id, "timestamp": now_utc(), "endpoint": endpoint,
        "customer_id": principal.get("subject_id"), "question_category": state.get("intent", ""),
        "question_redacted": redact(request.get("question", "")), "as_of_date": request.get("as_of_date"),
        "sources_retrieved": [{"doc_id": e.get("doc_id"), "section": e.get("section"), "score": e.get("score")}
                              for e in state.get("evidence", [])],
        "precedence_decisions": decisions,
        "rules_applied": state.get("rules_applied", []), "conflicts_detected": state.get("conflicts", []),
        "tools_invoked": [{"tool": s["tool"], "status": s.get("status"), "ms": s.get("ms"),
                           "input": s.get("input"), "output": s.get("output")} for s in tool_steps],
        "answer_type": response.get("answer_type"),
        "model": sorted({f"{u['provider']}:{u['model']}" for u in usage if u.get("llm_call")}),
        "llm_calls": sum(1 for u in usage if u.get("llm_call")),
        "tokens": sum(u.get("tokens_in", 0) + u.get("tokens_out", 0) for u in usage),
        "cache_hits": sum(1 for u in usage if u.get("cache_hit")),
        "latency_ms": round(latency_ms, 1), "flags": state.get("flags", []), "data_version": version,
        "steps": state.get("steps", []), "response": response,
    }


def _error_state(message: str) -> dict:
    return {"answer_type": policy.ABSTAIN, "answer": policy.NOT_FOUND_MESSAGE,
            "steps": [{"node": "service", "status": "error", "output": {"error": message[:300]}}]}


def answer(req: AskRequest, principal: dict, configurable: dict | None = None,
           endpoint: str = "/ask") -> tuple[dict, dict]:
    t0 = time.perf_counter()
    run_id = new_run_id()
    as_of = (req.as_of_date or date.today()).isoformat()
    request = {"question": req.question, "as_of_date": as_of}
    try:
        state = run_graph(run_id, request, principal, configurable)
    except GraphRecursionError:
        state = _error_state("recursion limit reached")
    except Exception as err:  # never a bare 500 for a question: contract-shaped answer + trace
        state = _error_state(f"{type(err).__name__}: {err}")
    response = build_response(run_id, state, as_of)
    record = build_audit(run_id, state, response, request, principal, (time.perf_counter() - t0) * 1000, endpoint)
    save_trace(record)
    return response, record


def stream_answer(req: AskRequest, principal: dict, endpoint: str = "/ask/stream"):
    """Yields {"event": "node", ...} per finished node, then {"event": "final", "response": ...}."""
    t0 = time.perf_counter()
    run_id = new_run_id()
    as_of = (req.as_of_date or date.today()).isoformat()
    request = {"question": req.question, "as_of_date": as_of}
    state: dict = {}
    try:
        init = {"run_id": run_id, "request": request, "principal": principal, "replans": 0}
        for mode, chunk in get_graph().stream(init, stream_mode=["updates", "values"]):
            if mode == "updates":
                for node, update in chunk.items():
                    steps = (update or {}).get("steps", [])
                    yield {"event": "node", "node": node,
                           "steps": [{k: s.get(k) for k in ("node", "tool", "status", "ms")} for s in steps]}
            else:
                state = chunk
    except Exception as err:
        state = _error_state(f"{type(err).__name__}: {err}")
    response = build_response(run_id, state, as_of)
    save_trace(build_audit(run_id, state, response, request, principal, (time.perf_counter() - t0) * 1000, endpoint))
    yield {"event": "final", "response": response}
