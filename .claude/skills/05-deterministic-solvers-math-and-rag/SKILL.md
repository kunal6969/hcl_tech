---
name: 05-deterministic-solvers-math-and-rag
description: Builds the deterministic core that earns most of the marks - pure, typed, unit-tested tools for lookups scoped to the caller, eligibility checks with explicit date-window conventions, Decimal money calculators with fee breakdowns, idempotent state-changing actions, what-if scenario overrides, [low, high] ranges, payback and ranking, LP/MILP optimisation, regression baselines, additive (Shapley) decompositions, idle and leak detection, and grounded retrieval (hybrid Chroma + BM25 with reciprocal-rank fusion, effective-date and supersession filtering, evidence sufficiency for abstention). Use this whenever an answer needs a number, a date, a yes/no decision, a ranking, a plan, a citation, or a "why did X change" split - and whenever a test or judge question involves edge cases such as last day of a window, approval limits, discounts, ambiguity or what-if.
---

# Deterministic tools, solvers and grounded retrieval

Disqualification line in both reference briefs: authoritative results "produced only by LLM text".
So every number, date, verdict, ranking and plan comes from a function in this skill, with a unit test
whose expected value was derived by hand from the statement. The LLM only picks tools and explains outputs.

- Analytics recipes (cleaning 15-min data, tariff pricing, regression baseline, exactly-additive bill
  bridge, idle/leak detection, savings ranges, explaining a re-run): `references/decomposition-baseline-and-anomaly-recipes.md`
- Thresholds come from the rule registry (skill 04 reference): `get_rule(...)` — never constants.

## 1. Tool contract (every tool, every problem)

1. Pure function `fn(args: InputModel, ctx: ToolContext) -> dict | BaseModel`; registered with a one-line
   planner description (skill 01 registry). No LLM calls inside tools.
2. Input models never contain identity; personal tools set `needs_identity=True` and read
   `ctx.principal["subject_id"]`.
3. Output carries: the result, a `reason_code`, the inputs actually used, units, and the lifted keys
   `rules_applied`, `conflicts`, `assumptions`, `evidence` when relevant (the graph copies them to the trace).
4. Money in `Decimal`, quantised once at the end (`ROUND_HALF_UP`, 2 dp) and returned as float; percentages
   stored as fractions; state the rounding rule in README.
5. Dates: `as_of` comes from the request (`ctx.as_of`), never `date.today()` inside a tool. Window rule
   written once, tested at the boundary: `days = (as_of - delivered_on).days; eligible = days <= window`
   (day N of an N-day window is eligible) — cite the clause; if the document says otherwise, follow it.
6. What-if: explicit optional override fields (`assume_days_since_delivery`, `assume_tier`,
   `tariff_override`) that the tool echoes in `assumptions`. The LLM never adjusts a number itself.
7. Ambiguity: return `{"needs_clarification": "<one short question>", "options": [...]}` — the graph
   turns it into `clarification_needed` (two orders of the same product, missing period, etc.).
8. Not-yours / not-found: raise `PermissionError` for both, with the same message, so responses never
   reveal whether another user's record exists.
9. State changes: re-check eligibility inside the tool, use an idempotency key, run in one transaction,
   return the existing record on a repeat call (`already_exists: true`).

## 2. Shared helpers

**`app/tools/common.py`** — Decimal money, as_date, add_months, Range, payback_months, rank_actions (58 lines). Installed by `python .claude/bootstrap.py`; source: `.claude/templates/app/tools/common.py`. Read it only when you need to edit it.

## 3. Personal-data tools (orders/accounts style) — pattern to adapt

Adapt table and column names to the statement's schema. The SQL is always scoped by the principal.

**`app/tools/example_orders.py`** — PATTERN to adapt: scoped lookup, eligibility, refund, warranty, idempotent create_return (122 lines). Installed by `python .claude/bootstrap.py`; source: `.claude/templates/app/tools/example_orders.py`. Read it only when you need to edit it.

## 4. Grounded retrieval: hybrid index + search tool

Dense (sentence-transformers via Chroma) catches paraphrases; BM25 catches exact clause words and IDs;
reciprocal-rank fusion combines them without score calibration. `EMBEDDINGS=hash` gives a dependency-free
lexical embedder for tests and MOCK runs. Collection names include the embedder name so switching models
never collides with a persisted collection.

**`app/rag/index.py`** — HybridIndex: Chroma dense + BM25 sparse with reciprocal-rank fusion, hash embedder for offline tests (114 lines). Installed by `python .claude/bootstrap.py`; source: `.claude/templates/app/rag/index.py`. Read it only when you need to edit it.

**`app/tools/search.py`** — search_documents: date/scope/supersession filtering + evidence sufficiency (59 lines). Installed by `python .claude/bootstrap.py`; source: `.claude/templates/app/tools/search.py`. Read it only when you need to edit it.

Abstention logic: `sufficient=False` returns no evidence; with no other tool result the graph answers
the statement's not-found message. Tune `min_overlap` and `top_k` through `configurable` and compare
in the eval (an easy, honest A/B). When evidence is partial, the synthesizer says what is and isn't covered.

Embedding choice line for the Q&A: all-MiniLM-L6-v2 is faster and smaller; bge-small-en-v1.5 usually
retrieves better on policy text (prefix queries with "Represent this sentence for searching relevant
passages: " when using bge). Measure both on retrieval hit rate rather than asserting.

## 5. Optimisation (plans, schedules, allocations)

```python
from scipy.optimize import milp, LinearConstraint, Bounds
import numpy as np
# maximise saving subject to budget: choose actions x_i ∈ {0,1}
c = -np.array([a["saving_mid"] for a in actions])                 # milp minimises
budget = LinearConstraint(np.array([[a["capex_high"] for a in actions]]), ub=[BUDGET])
res = milp(c, constraints=[budget], integrality=np.ones(len(actions)), bounds=Bounds(0, 1))
chosen = [a for a, x in zip(actions, res.x) if x > 0.5]          # report res.status and the binding constraint
```

Return the plan, the objective value, which constraints bind, and what would change the plan
(e.g. budget +10%). Re-plan = re-run with new inputs; diff the two plans in a tool, not in prose.

## 6. Testing pattern

**`tests/test_tools_examples.py`** — from datetime import date (78 lines). Installed by `python .claude/bootstrap.py`; source: `.claude/templates/tests/test_tools_examples.py`. Read it only when you need to edit it.

**`tests/test_search_tool.py`** — import pytest (42 lines). Installed by `python .claude/bootstrap.py`; source: `.claude/templates/tests/test_search_tool.py`. Read it only when you need to edit it.

## 7. Verification checklist

- [ ] Every threshold a tool uses comes from `get_rule` and appears in `rules_applied` with its clause.
- [ ] Boundary tests: last day eligible, next day not; refund on net (discounted) price; approval limit
      exactly at, below, above; zero-warranty products; undelivered orders; existing returns.
- [ ] Other-user and missing records produce identical tool output.
- [ ] What-if overrides never touch stored data and always appear in `assumptions`.
- [ ] Analytics bridges sum exactly to the total (property test) and every saving is a `[low, high]` range.
- [ ] Retrieval: hit rate measured on paraphrased questions; superseded/expired/unofficial text never
      cited as current; upcoming documents mentioned, not applied.
