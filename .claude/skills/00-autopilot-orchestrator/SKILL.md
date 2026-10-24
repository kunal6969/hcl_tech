---
name: 00-autopilot-orchestrator
description: Runs the whole one-day hackathon build on autopilot. Reads a newly dropped problem statement, extracts a requirements traceability matrix, runs a one-batch pre-flight interview, picks the simplest architecture, plans time from the scoring rubric, then drives Stages 1-6 (skeleton + contract, data + ingest, deterministic core, LangGraph + LLM, evaluation, UI + deliverables + freeze) with test gates, self-healing fixes, commits and handoff updates. Use this whenever a problem statement, participant guide, brief, PDF/DOCX or dataset appears in problem/ or the chat; whenever the user says start, go, continue, next, plan, what now, status, late data drop, new file arrived, code freeze, demo prep or judge Q&A; and whenever HANDOFF_STATE.md shows status NOT_STARTED, PREFLIGHT or STAGE_n - even if the user never names this skill.
---

# Autopilot orchestrator

You are the tech lead. The user should only need to drop the statement and answer one batch of
questions; you decide, build, test, commit and report at stage boundaries. Every decision optimises the
judges' rubric: correctness and grounding first, simplest architecture, measured evaluation, a demo
that works live, and teammates who can explain everything.

Skills you route to: 01 graph · 02 UI · 03 LLM gateway · 04 data/ingest/registry · 05 tools/analytics/RAG ·
06 API/trace/Docker · 07 eval/deliverables · `handoff` · `resume`.
Code blocks headed `# file: <path>` in those skills are tested templates: copy verbatim, then adapt.

## S0 — Pre-flight (target 15–20 min)

1. **Read the statement completely.** PDF: Read tool (page ranges if long). DOCX:
   `python -c "import docx,sys; print('\n'.join(p.text for p in docx.Document(sys.argv[1]).paragraphs))" problem/<file>.docx`
   (tables: `pandoc -t gfm`). Save the text to `docs/STATEMENT.md` for grep.
2. **Write `docs/REQUIREMENTS.md`** with the template below. Copy contracts, enums, messages, schemas,
   precedence/analysis rules and deliverables **verbatim**. Number every requirement (R1…) if the statement doesn't.
3. **Classify the archetype** (sets the component list):

   | Archetype | Signals | Core components |
   |---|---|---|
   | A. Grounded policy assistant | documents, citations, versions, customer data, eligibility, refunds | 04 docs + registry + precedence, 05 search + personal tools, 06 identity |
   | B. Quantitative diagnostic | time series, "why did X change", baseline, waste, savings ranges | 04 time series, 05 analytics recipes (bridge, idle/leak, savings) |
   | C. Planner / optimiser | constraints, objective, schedule/allocation, re-plan | 05 LP/MILP + what-if, diff of plans |
   | D. Hybrid | several of the above | combine; still one graph |

4. **Detect the environment yourself** (don't ask): `python --version`, `git status`, `docker --version`,
   `ollama list`, which keys exist in `.env` (print booleans only:
   `python -c "from dotenv import dotenv_values as d; print({k: bool(v) for k, v in d('.env').items()})"`).
5. **Interview — one batch, ≤ 6 questions** (AskUserQuestion tool if available, else one numbered
   message). Ask only what the statement and environment can't tell you:
   - Team: how many members, who owns which area (so each member commits and can explain a part)?
   - Clock: current time and code-freeze time if not in the statement; any late data drop time?
   - Kickoff/mentor clarifications not in the document?
   - LLM access confirmed (Ollama model pulled / Gemini / Groq / other) vs what the statement permits?
   - Data: is the data pack in `problem/`, and must we generate any data ourselves?
   - One genuinely ambiguous point in the statement that changes the design (offer 2–3 options).
   If the user doesn't answer quickly, proceed with defaults and record them as assumptions.
6. **Architecture decision** with skill 01's matrix → `docs/ARCHITECTURE.md` (tier, Mermaid diagram,
   "why not more agents", requirement IDs per component) and lines in `docs/DECISIONS.md`.
7. **LLM compliance** with skill 03 §0 → `.env.example`, README disclosure stub.
8. **Time plan** (below) into HANDOFF_STATE.md; set `status: STAGE_1`; append PROGRESS_LOG; commit
   `chore(preflight): requirements, architecture, plan`.

### REQUIREMENTS.md template

```markdown
# REQUIREMENTS — <title>   (source: problem/<file>, extracted <UTC time>)
## 1 Mission (verbatim key sentence) and archetype
## 2 Mandated stack (layer | required | allowed alternatives | our choice)
## 3 API contract — endpoint table, headers, request bodies, response JSON example, answer types + fixed messages (ALL VERBATIM)
## 4 Traceability matrix
| ID | Requirement (short, verbatim words) | Component (file) | Evidence (test / eval case) | Stage | Status |
## 5 Data: schemas (verbatim), minimums, edge cases (each → handling → test id), reserved IDs
## 6 Rules annex (precedence policy / analysis rules / worked examples — verbatim; each worked example becomes a test)
## 7 Evaluation minimums (category → count → case ids) + metrics to report + method
## 8 Scoring rubric (criterion | points | what we must show | evidence) → drives the time plan
## 9 Disqualification conditions (verbatim) → the guard that prevents each
## 10 Demo must-show list → DEMO_SCRIPT items
## 11 Live judge tests (what they will do) → rehearsal checklist
## 12 Deliverables (verbatim) → file paths
## 13 Schedule & key times (kickoff, late drop, freeze, demo)
## 14 Open questions → chosen interpretation (also in README assumptions)
```

### Time plan

Allocate remaining minutes until freeze minus a 10% buffer. Default split, then shift weight toward the
stages that carry the most rubric points (map each criterion to the stage that earns it):

| Stage | Default share | Exit gate (all must hold) |
|---|---|---|
| S1 Skeleton + contract | 10% | contract tests green with MOCK_LLM; `/health` ok; one request returns a contract-valid JSON with a trace |
| S2 Data + ingest | 15% | validation report written; loader loads the pack; `/ingest` table + document round trips; data version bumps |
| S3 Deterministic core | 25% | every tool/solver has hand-derived golden tests incl. each statement edge case; worked examples pass |
| S4 Orchestration + LLM | 20% | e2e test per answer type (MOCK); live smoke of statement examples; guard in every trace |
| S5 Evaluation | 15% | ≥ minimum cases per category; report with all metrics + method + A/B decision |
| S6 UI + deliverables + freeze | 15% | UI demo path works; all deliverables exist; `docker compose up` from clean clone; tag `final` |

## Stage playbook

**S1 Skeleton + contract** (skills 06, 03, 01). Start with one command, not with typing code:

```bash
python .claude/bootstrap.py --tier core            # + data / tools / analytics / agents / ui / eval as stages need them
pip install -r requirements.txt
MOCK_LLM=true pytest -q                            # the installed skeleton is already green
```

That installs the tested gateway, guard, graph, registry, API, trace store, Docker files and their tests,
writes `pyproject.toml` and `.gitignore`, and prints which files are problem-specific stubs to edit.
Then edit for this problem: `app/api/schemas.py` (contract verbatim), `app/graph/policy.py` (answer types,
messages, regexes), `app/tools/catalog.py`. Add anything else the layout needs:
`.env.example`, `.gitignore` (`data/`, `.env`, `__pycache__/`, `eval/reports/*.json`), `pyproject.toml` with
`[tool.ruff] line-length = 120` and `[tool.pytest.ini_options] pythonpath = ["."]`; schemas verbatim; service +
trace store; gateway (MOCK); graph with policy stub; `tests/test_api_contract.py`; Dockerfile + compose.
Commit, `git tag stage-1`.

**S2 Data + ingest** (skill 04): `python .claude/bootstrap.py --tier data` (add `tools` for the example
domain tools, `analytics` for archetype B), then TableSpecs from the schema annex with row rules for every logical
constraint; validation CLI + report; loader CLI exactly as the statement names it; seed documents through
`ingest_document`; rule registry seeded with clause references; synthetic data generator if required
(+ prompts saved verbatim); data card stub. Tag `stage-2`.

**S3 Deterministic core** (skill 05 + its reference): one tool per capability row of the statement;
thresholds via `get_rule`; tests first with hand-computed values from the statement's worked examples and
edge cases; property tests (bridges add up, ranges ordered). This stage earns the most points — don't
rush it to get to the LLM. Tag `stage-3`.

**S4 Orchestration + LLM** (skills 01, 03): fill `policy.py`; register tools in `app/tools/catalog.py`;
rules for every example question shape; planner for the rest; per-intent templates; live smoke with the
real provider; check traces show model/tokens/latency. Tag `stage-4`.

**S5 Evaluation** (skill 07): write cases from REQUIREMENTS §7 before running; run; fix **general** causes
only; A/B one honest knob (top_k, min_overlap, chunk size, embedding model, model); final run with
`LLM_CACHE=false`. Tag `stage-5`.

**S6 UI + deliverables + freeze** (skills 02, 07): UI (≤ 45 min), README, data card, AI usage,
contributions, declaration, traces export, demo script, Q&A crib; clean-clone `docker compose up`; tag `final`.

Token discipline (CLAUDE.md §2b): install templates, never retype them; read a template only to edit it;
keep tool output short; run `handoff` and `/clear` at stage boundaries.

After **every** stage: run `ruff check --fix . && pytest -q`, commit, update HANDOFF_STATE.md (stage board,
next 3 actions, coverage), append PROGRESS_LOG.md, and post a ≤ 5-line status to the user.

## Subagent delegation (keeps the main session lean)

When you need to read a large file, explore the codebase, run a verbose test suite, or generate
documentation, delegate to a subagent (`context: fork`) so the output stays out of the main context:
- "Read app/analytics/bridge.py and summarise the decomposition algorithm" → subagent
- "Run pytest -v and report only the failures with their tracebacks" → subagent
- "Generate the data card from the prompts in data_gen/" → subagent
The main session gets a clean summary; the verbose output is discarded with the subagent.

## Self-healing loop (every change, every stage)

```
run: ruff check --fix . && pytest -q -x
green → commit → continue
red → read the first failure fully → classify:
  ImportError / missing module   → fix import or add + pin dependency (note in DECISIONS.md)
  contract test                  → schema drifted from the statement: fix the model/mapping, never the test
  golden-value test              → recompute the expected value by hand from the source FIRST; fix code if the
                                   test is right; change a golden value only with a written derivation
  flaky / network                → the test must use MOCK_LLM, hash embeddings and temp stores
apply the smallest fix → re-run that file → re-run the suite
same failure 3 times → git stash push -m "wip: <failure>" → mark BLOCKED in HANDOFF_STATE + PROGRESS_LOG →
  tell the user the error and two options → continue with the next independent task meanwhile
```

Never: delete or weaken an assertion to go green, special-case a test/eval input, catch-and-ignore to hide
an error, or skip the suite before a commit. (Hard-coded answers are a disqualification condition.)

## Interrupt protocols

**Late data drop / new file / schema change**: save the original under `problem/late/`; run the
validation CLI and show the report; snapshot canonical responses (`eval/reports/before_v<N>.json`); ingest
via loader or `/ingest`; re-run; diff (skill 05 `diff_bridges` or plan diff); write `docs/CHANGES_v<N+1>.md`;
add an eval case; commit `feat(data): late drop v<N+1> [R..]`; tell the user what changed and why.

**Judge-style live ingest rehearsal** (before S6 ends): write a document the system has never seen (e.g. a
circular that changes a threshold, effective today, superseding a clause) and a CSV with an extra column and
two bad rows; ingest both through HTTP; ask questions; confirm behaviour changed with no restart.
Put the exact steps in the demo script.

**Code freeze countdown**: T-60 no risky refactors · T-40 full eval + README numbers · T-25 clean-clone
`docker compose up` · T-15 export traces + deliverables · T-5 final commit, `git tag final`, `status: FROZEN`.

**Provider outage / quota**: switch chain via env (skill 03), keep MOCK templates presentable, note in README.

**Mentor clarification**: record verbatim in REQUIREMENTS §14, update the interpretation, add a test.

## Demo and Q&A preparation (S6)

- `docs/DEMO_SCRIPT.md`: each must-show item → exact input → expected answer type → trace ID from the
  last real run → one sentence to say. Add the live-ingest rehearsal and a what-if.
- `docs/QA_CRIB.md`: per component — purpose, why this design, rejected alternative, failure modes, the
  file/function to change for a likely live request, its tests. Assign each teammate a section to own.
- Rehearse the "small live change" drills: change a threshold in the registry, add an answer type to
  policy, switch provider via env, change `top_k` via configurable, add a row rule to a TableSpec.

## When behind schedule — cut in this order

1. UI polish → plain Streamlit components. 2. SSE streaming → post-hoc trace replay. 3. Tier 3 agents →
Tier 2. 4. A/B with a third config → two configs. 5. OCR → report `indexed_empty_text` honestly.
Never cut: verbatim contract, deterministic tools with tests, abstention/refusal, `/ingest`, traces,
the eval with required categories, README with run steps.

## Status message format (to the user, at stage boundaries)

```
S3 ✅ deterministic core — 24 tests green (tag stage-3, a1b2c3d)
Covered: R4 precedence (worked example passes), R5 refund/eligibility/warranty tools, edge cases E1–E9
Decisions: window rule = inclusive (clause 3.1); refund on net price (data schema note)
Next (S4, ~70 min): policy rules for 7 question shapes, planner, guard, live smoke on Gemini
Blockers: none
```
