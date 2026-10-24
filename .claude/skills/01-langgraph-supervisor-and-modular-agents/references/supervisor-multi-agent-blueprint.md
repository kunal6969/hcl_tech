# Supervisor + specialist agents (Tier 3)

Use only when the decision matrix in SKILL.md says so, and write the justification (requirement IDs)
into `docs/ARCHITECTURE.md` before building. It reuses everything from the unified blueprint —
state, tool registry, policy, `input_guard`, `synthesize` (with the faithfulness guard) and `finalize` —
so switching tiers is a change to `build.py`, not a rewrite.

```
START → input_guard → supervisor ──Command(goto)──▶ retrieval_agent ─┐
                         ▲   │                       analytics_agent ─┤ (each returns to supervisor)
                         │   │                       action_agent  ───┘
                         └───┘ max 4 turns
                             └──▶ synthesize (LLM + faithfulness guard) → finalize → END
```

## When Tier 3 is honestly justified

- The request mix needs **heterogeneous capabilities in an order that can't be enumerated** in advance
  (e.g. retrieve → discover a rule → compute → decide whether to act), and a single planned list keeps failing.
- Specialists need **different tool sets and prompts** that would bloat one planner prompt (small local models
  plan much better with 3–4 tools than with 15).
- **Parallel work** pays off: independent retrieval and analytics for one request (fan-out with `Send`).
- A state-changing **action must be isolated** behind its own eligibility check and confirmation.

If none of these is true, stay on Tier 1/2 and say so in the Q&A: "we deliberately did not add agents
because each step is deterministic" is a scoring line in the brief.

## Code

**`app/graph/supervisor.py`** — Tier 3 only: supervisor with Command routing, workers with tool allow-lists, Send fan-out (131 lines). Installed by `python .claude/bootstrap.py`; source: `.claude/templates/app/graph/supervisor.py`. Read it only when you need to edit it.

Notes that judges probe:

- **Bounded autonomy**: `MAX_TURNS`, each worker runs once, workers can't call tools outside their allow-list.
- **One synthesizer, one guard**: workers never talk to the user; only `synthesize` writes prose, and the
  faithfulness guard checks it. Every number still comes from a tool.
- **Supervisor LLM is optional per turn**: with a single pending worker the choice is deterministic,
  so a typical request costs 1 planner call + 1 synthesis call, same as Tier 1.
- **Action isolation**: `action_agent` is excluded from parallel fan-out and its tools must re-check
  eligibility and be idempotent (skill 05 §2.4).

## Test

**`tests/test_graph_supervisor.py`** — import pytest (43 lines). Installed by `python .claude/bootstrap.py`; source: `.claude/templates/tests/test_graph_supervisor.py`. Read it only when you need to edit it.
