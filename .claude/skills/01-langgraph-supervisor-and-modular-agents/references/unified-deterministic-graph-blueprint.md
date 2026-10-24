# Unified deterministic graph (Tier 1) + planner–executor (Tier 2)

Default architecture. One `StateGraph`, five nodes, one LLM call for planning (only when the
deterministic rules don't match) and one for the explanation. Everything authoritative happens in
tools. Copy the `# file:` blocks verbatim, then edit only `app/graph/policy.py` and your tools.

```
START → input_guard ─┬─▶ route ─┬─▶ execute ─┬─▶ synthesize ─▶ finalize ─▶ END
                     │          │     ▲      │   (LLM + faithfulness guard)
                     │          │     └──────┘ replan once on tool error
                     └──────────┴──────────────────────────────▶ finalize   (refuse / clarify / abstain)
```

Contents: 1 State · 2 Tool registry · 3 Policy (the only problem-specific file) · 4 Nodes ·
5 Build + run · 6 Faithfulness guard · 7 Tests · 8 Tier 2 notes · 9 Streaming

## 1. State

**`app/graph/state.py`** — GraphState TypedDict with operator.add reducers (32 lines). Installed by `python .claude/bootstrap.py`; source: `.claude/templates/app/graph/state.py`. Read it only when you need to edit it.

## 2. Tool registry

Tools are pure Python with a Pydantic input model. Identity never appears in an input model: tools read
it from `ToolContext.principal`, so an LLM-planned argument can never impersonate another user.
A tool may return these optional keys, which `execute` lifts into state: `evidence`, `rules_applied`,
`conflicts`, `assumptions`.

**`app/tools/registry.py`** — ToolSpec/ToolContext/run_tool: validation, authorisation, never raises, returns a trace step (59 lines). Installed by `python .claude/bootstrap.py`; source: `.claude/templates/app/tools/registry.py`. Read it only when you need to edit it.

## 3. Policy — the only problem-specific file in the graph

Fill it from `docs/REQUIREMENTS.md`: answer-type names and fixed messages verbatim, ID formats from the
data schema, the intents the statement lists, and deterministic rules for the common question shapes
(they make routing free, fast and testable; the LLM planner only handles the long tail).

**`app/graph/policy.py`** — the ONLY problem-specific graph file: answer types, messages, entity regexes, intent rules, template answers (84 lines). Installed by `python .claude/bootstrap.py`; source: `.claude/templates/app/graph/policy.py`. Read it only when you need to edit it.

## 4. Nodes

**`app/graph/nodes.py`** — input_guard, route, execute, synthesize (+guard), finalize, and the plan/ref helpers (227 lines). Installed by `python .claude/bootstrap.py`; source: `.claude/templates/app/graph/nodes.py`. Read it only when you need to edit it.

Why `execute` takes `config`: LangGraph passes the run config to a node whose signature has a
`config` parameter; `configurable` carries per-request knobs (top_k, scenario overrides, A/B settings)
without touching state. Type it exactly `config: RunnableConfig` with no default: under
`from __future__ import annotations`, `config: RunnableConfig | None = None` silently receives `None`
(verified on langgraph 1.2).

## 5. Build and run

**`app/graph/build.py`** — graph wiring, get_graph(), run_graph(), mermaid() (39 lines). Installed by `python .claude/bootstrap.py`; source: `.claude/templates/app/graph/build.py`. Read it only when you need to edit it.

## 6. Faithfulness guard

Runs at the end of `synthesize` and again in the eval harness (metric "number faithfulness").
It removes IDs (O-100001, SKU-E001, CO2e, Q3, v1.0), list markers and "step 2"-style references, then
checks every remaining number and ISO date against FACTS + the question, accepting rounded forms
(2639.1 → 2,639 / 2,640 / 2,600), fraction↔percent (0.38 → 38%), magnitude words (14.4k, 1.2 lakh)
and Indian digit grouping (1,23,456).

**`app/llm/guard.py`** — the faithfulness guard: check_faithfulness(text, facts, question) -> {ok, unsupported, checked} (86 lines). Installed by `python .claude/bootstrap.py`; source: `.claude/templates/app/llm/guard.py`. Read it only when you need to edit it.

## 7. Tests (MOCK_LLM — no network)

**`tests/test_graph_unified.py`** — import pytest (67 lines). Installed by `python .claude/bootstrap.py`; source: `.claude/templates/tests/test_graph_unified.py`. Read it only when you need to edit it.

## 8. Tier 2 — planner–executor notes

The graph above already is a planner–executor: rules or the LLM produce a validated plan, `execute`
runs it deterministically, one bounded replan handles tool errors. To support richer multi-step and
what-if requests:

- Give tools explicit scenario arguments (`assume_days_since_delivery`, `assume_tier`, `tariff_override`)
  and have them echo `assumptions` in their output. Never let the LLM change a number "in its head".
- Allow references between steps (`"$0.output.order_id"`) — `_resolve_refs` handles it.
- Keep `MAX_PLAN_STEPS` ≤ 6 and `MAX_REPLANS` = 1: bounded cost, explainable behaviour.
- For "compare A vs B" what-ifs, plan the same tool twice (baseline + scenario) and let the
  synthesizer contrast two tool outputs; the difference must also come from a tool if it is quoted.

## 9. Streaming node events to the UI (optional)

```python
def stream_events(run_id: str, request: dict, principal: dict):
    """Yield one dict per finished node, then the final state (for an SSE endpoint)."""
    from app.graph.build import get_graph
    state = {"run_id": run_id, "request": request, "principal": principal, "replans": 0}
    final: dict = {}
    for mode, chunk in get_graph().stream(state, stream_mode=["updates", "values"]):
        if mode == "updates":
            for node, update in chunk.items():
                yield {"event": "node", "node": node, "steps": (update or {}).get("steps", [])}
        else:
            final = chunk
    yield {"event": "final", "state": final}
```
