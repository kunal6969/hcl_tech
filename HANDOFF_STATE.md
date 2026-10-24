# HANDOFF_STATE
<!-- Single source of truth for continuity across sessions, teammates and Claude accounts.
Overwrite in place (skills `handoff` / `00-autopilot-orchestrator`). Keep <= 120 lines and ~6,000 chars
so the SessionStart hook injects it whole. Never put secrets here. -->

status: STAGE_3
updated_utc: 2026-10-24T07:00Z
updated_by: raghavsinghal941@gmail.com
reason: S1+S2 complete; 54 tests green; RAG seeded; tagged stage-2
code_freeze_local: TBD
last_green_commit: 1ba5876
problem_title: AI-Powered Hospital Patient Services Assistant
archetype: A grounded policy assistant
architecture: Tier 1 fixed graph (docs/ARCHITECTURE.md)
llm_chain: Groq llama-3.3-70b-versatile → Gemini Flash fallback; MOCK_LLM for tests

## Next 3 actions (exact, executable)
1. Wire real Groq/Gemini: add GROQ_API_KEY + GEMINI_API_KEY to .env, run live smoke test
2. Write eval/cases.yaml: 25 cases covering all 7 answer_type values + edge cases E1-E8
3. Build Streamlit UI (ui/streamlit_app.py): patient picker, chat, badges, citations, admin ingest

## Stage board
| Stage | State | Gate | Notes |
|---|---|---|---|
| S0 Pre-flight | done | docs/REQUIREMENTS.md + ARCHITECTURE.md written | |
| S1 Skeleton + contract | done | 9 contract tests green; /health ok; MOCK e2e ok | commit 1ba5876 |
| S2 Data + ingest | done | SQLite 8 tables/20 rows; ChromaDB 21 chunks; 54 tests green | tag stage-2 |
| S3 Deterministic core | in_progress | 23 tool golden tests pass; graph e2e green (MOCK) | need live LLM smoke |
| S4 Orchestration + LLM | todo | e2e per answer type, guard in traces, live smoke | |
| S5 Evaluation | todo | >=25 eval cases, report, A/B | eval/cases.yaml stub exists |
| S6 UI + deliverables | todo | demo path, deliverables, docker compose up, tag final | |

## Requirements coverage (R-id | status | evidence)
R1 policy retrieval | green | ChromaDB search, retrieve node, test_api_contract
R2 citations | green | compose node builds citations from chunks; contract test
R3 grounding | green | compose system prompt, output_guard answer_type check
R4 conflict resolution | green | authority_score in policy.py; resolve node
R5 tools | green | 5 tools in hospital.py; 23 golden tests pass
R6 abstention | green | not_found + not-found message verbatim in schemas.py
R7 identity from headers | green | X-Patient-Id + X-Role; input_guard cross-patient check
R8 injection guard | green | is_injection in policy.py; input_guard node
R9 audit trace | green | write_audit in trace/store.py; audit_writer node
R10 live ingest | green | /admin/ingest endpoint; ingest_docs.py
R11 health | green | /health endpoint checks SQLite + ChromaDB + MOCK flag

## Key decisions (one line each; details in docs/DECISIONS.md)
D1: Identity from X-Patient-Id + X-Role headers only (not JWT — simpler for hackathon)
D2: Groq (llama-3.3-70b-versatile) main + Gemini Flash fallback
D3: Keyword-first router with LLM fallback for unclassified questions
D4: One-step reschedule — validate date + slot, then update or refuse
D5: Newest ingested wins conflict ties (authority_rank > version > effective_date > ingested_at)
D6: Core 4 tools + reschedule (5 total); pre-op = compose of lab + protocol + eligibility
D7: SQLite for structured data; ChromaDB for policy docs
D8: Tier 1 fixed graph — no planner/multi-agent (simplest architecture that meets all R-ids)

## Run commands
- Seed DB: `python scripts/seed_db.py`
- Seed docs: `EMBEDDINGS=hash python scripts/seed_docs.py`
- API: `uvicorn app.api.main:app --reload --port 8000`
- UI: `streamlit run ui/streamlit_app.py`
- Tests: `MOCK_LLM=true EMBEDDINGS=hash pytest -q`
- Eval: `python eval/run_eval.py --mode http --base-url http://localhost:8000`

## Open issues / blockers
- Real LLM keys needed in .env for live smoke test (S4)
- eval/cases.yaml has 5 placeholder cases; needs 25 proper cases (S5)

## Eval scoreboard (latest: metric | value | commit)
Not run yet

## Gotchas learned (things a fresh session must not rediscover)
- chromadb 1.5.9: _HashEmbeddingFunction MUST subclass EmbeddingFunction[Documents]; name() must be @staticmethod
- Windows cp1252: use ASCII [OK]/[FAIL] not Unicode check marks in seed scripts
- Bootstrap template tests (test_gateway, test_graph_unified, test_search_tool, test_graph_supervisor, test_precedence) are for a generic supervisor arch — skip them with pytest.skip at module level
- data/chroma must be cleared before re-seeding if embedding function changes
