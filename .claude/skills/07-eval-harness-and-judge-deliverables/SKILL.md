---
name: 07-eval-harness-and-judge-deliverables
description: Builds the mandatory evaluation and every judge-facing deliverable - a 20+ case YAML eval set mapped to the statement's category minimums (unanswerable, conflicts/versions, personal tool cases incl. boundary dates and fees, cross-user access, multi-step and what-if, injection, invent-a-number, paraphrases), a runner that hits the live API or runs in-process, metrics (answer and tool correctness, citation accuracy, abstention accuracy, retrieval hit rate, refusal accuracy, number faithfulness, p50/p95 latency, LLM calls and tokens), an A/B config comparison with a written choice, plus README, data card, AI-usage disclosure, contribution statement, declaration, sample traces, demo script and Q&A crib sheet. Use this whenever the user mentions evaluation, test set, metrics, accuracy, latency, comparing configurations, README, deliverables, submission, data card, traces export, demo prep, or code freeze.
---

# Evaluation harness + judge deliverables

"A system with no evaluation is incomplete" and "no evaluation of any kind" disqualifies. The eval is
also the safety net for every change after S4: run it after each fix, never tune to individual cases.

## 1. Build the case set from REQUIREMENTS §7

Make a coverage table first (category → minimum → case IDs), then write cases. Rules:
- Every statement minimum is met with ≥ 1 spare; total ≥ 25 so a few failures don't drop a category to zero.
- ≥ 30% of questions **reworded away from the documents' wording** (paraphrases, typos, Hinglish if the
  audience is Indian customers) — a set that repeats the documents overstates quality.
- Expected values are computed **by hand from the statement/documents/data**, written before running,
  never copied from system output.
- Include adversarial cases: other-user IDs, injection in a document/note/question, "just guess a number",
  "ignore the policy", future-dated documents, a document that conflicts at equal authority.
- Analytics problems: ≥ 3 cases where the right answer blames price or mix (not machines); numeric cases
  with tolerances; what-if cases (lower tariff, different mix); out-of-data questions.

**`eval/cases.example.yaml`** — case-file format; copy to eval/cases.yaml and write the problem's cases (35 lines). Installed by `python .claude/bootstrap.py`; source: `.claude/templates/eval/cases.example.yaml`. Read it only when you need to edit it.

## 2. Runner (same code for live HTTP and in-process A/B)

**`eval/run_eval.py`** — the eval runner: http/in-process callers, metrics, A/B, markdown report (227 lines). Installed by `python .claude/bootstrap.py`; source: `.claude/templates/eval/run_eval.py`. Read it only when you need to edit it.

A/B configs (in-process, same cases, same commit):

**`eval/configs.example.yaml`** — A/B config format (4 lines). Installed by `python .claude/bootstrap.py`; source: `.claude/templates/eval/configs.example.yaml`. Read it only when you need to edit it.

Write the decision under the table in `eval/reports/latest.md`: which config won on which metric,
the trade-off (e.g. +8% retrieval hit, +300 ms p95), and why the final choice is what ships.

Optional LLM-as-judge (for free-text quality only, never for numbers): prompt = question, expected
answer, system answer → `{"verdict": "correct|partial|wrong", "reason": "..."}` via the gateway with a
schema. Calibrate it on 8 hand-labelled cases and report the agreement rate next to its scores.

## 3. Tests for the runner

**`tests/test_eval_runner.py`** — import sys (35 lines). Installed by `python .claude/bootstrap.py`; source: `.claude/templates/tests/test_eval_runner.py`. Read it only when you need to edit it.

## 4. Deliverables (generate in S6; keep each to what the statement asks)

| Statement asks for | File | How |
|---|---|---|
| README: diagram, setup/run, curl samples, assumptions, limitations, edge cases | `README.md` | template below; Mermaid from `app.graph.build.mermaid()` |
| docker compose up works | `docker-compose.yml` | skill 06; test from a clean clone |
| Source register / data files / validation output | `source_register.csv`, `docs/validation_report.md` | `GET /sources` → CSV; `python -m app.data.validate` |
| Rule registry linked to clauses | SQLite `rule_registry` + `docs/RULES.md` | export table with doc/section columns |
| Synthetic data kit / data card | `data_gen/`, `docs/DATA_CARD.md` | prompts verbatim, generator, validator output |
| Evaluation set + report | `eval/cases.yaml`, `eval/reports/latest.md` | this skill |
| Three sample audit/trace records (different answer types) | `deliverables/traces/*.json` | `scripts/export_traces.py` |
| AI-usage disclosure | `docs/AI_USAGE.md` | template |
| Team contribution statement | `docs/CONTRIBUTIONS.md` | `git shortlog -sne` + ownership table |
| Declaration of original work | `docs/DECLARATION.md` | template, every member signs |

**`scripts/export_traces.py`** — export one trace per answer type for the submission (17 lines). Installed by `python .claude/bootstrap.py`; source: `.claude/templates/scripts/export_traces.py`. Read it only when you need to edit it.

README skeleton (fill every section from real runs; no claims without evidence):

```markdown
# <Project name> — <one-line mission from the statement>
## Architecture
<Mermaid graph from mermaid()> + 5 sentences: tier chosen and why (requirement IDs), what the LLM does, what tools do.
## Quick start
cp .env.example .env  →  docker compose up  →  open http://localhost:8501 ; API on :8000 (Ollama on host: `ollama serve`).
Local dev: `pip install -r requirements.txt && uvicorn app.api.main:app --reload` · tests: `pytest -q` · MOCK_LLM=true for offline.
## Data
Loader: `python scripts/load_data.py --dir <folder>` · validation: `python -m app.data.validate --dir <folder>` · /ingest examples.
## API (curl samples for every endpoint)
## Evaluation (table from eval/reports/latest.md + method + A/B decision)
## Assumptions | Limitations | Known edge cases (each with how the system handles it)
## LLM disclosure (provider chain, models, when cloud fallback is used)
## Team & contributions → docs/CONTRIBUTIONS.md
```

Data card fields (use the statement's annex headings exactly): purpose · generation method (model,
prompts verbatim, rounds, manual edits, seeds) · schema and validation (checks + output) · edge cases
(each with the ID that demonstrates it) · distribution (per tier/status/category or per meter/day) ·
known gaps and biases · privacy statement (no real person or company data).

AI-usage disclosure: which files/modules were drafted with which assistant (Claude Code, Copilot...),
how each was verified (tests written first, hand-computed golden values, code review by <member>), and
what was rejected. Contributions: table of member → components → key commits (`git log --author`).

## 5. Demo script + Q&A crib (S6, from real runs only)

`docs/DEMO_SCRIPT.md`: for each must-show item in the statement (e.g. cited answer, tool-based
eligibility + calculation, not-found, conflict resolved / cannot-decide case, data trap handled,
re-plan or what-if): exact question or curl, expected answer type, the trace ID from the last real run,
and the one sentence to say. Add the live-ingest rehearsal (new document or corrected file → behaviour
change without restart).

`docs/QA_CRIB.md`: per component — what it does, why this design, alternative rejected, failure modes,
the file/function a judge may ask to change live (threshold in registry, new answer type in policy,
provider switch via env, top_k via configurable), and its test.

## 6. Checklist before freeze

- [ ] ≥ statement minimum per category (+1 spare), ≥ 30% paraphrased, expected values hand-derived.
- [ ] `eval/reports/latest.md` has all required metrics, the method, and an A/B table with a decision.
- [ ] Final latency numbers measured with `LLM_CACHE=false`.
- [ ] No case passes because of special-casing; any fix touched general logic and re-ran the whole set.
- [ ] Every deliverable in the table exists, and README commands were run from a clean clone.
