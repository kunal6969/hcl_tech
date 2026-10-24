# REQUIREMENTS — AI-Powered Hospital Patient Services Assistant
Source: Hospital_AI_Assistant_Use_Case.pdf, extracted 2026-10-24 UTC

## 1. Mission and Archetype
**Mission**: Build an AI-powered Hospital Patient Services Assistant that answers questions and performs
authorized healthcare service actions using hospital policies, patient records, insurance information,
schedules, reports and operational systems. Responses must be accurate, grounded, explainable and secure,
and the assistant must never generate unsupported medical facts.

**Archetype**: A — Grounded policy assistant with deterministic tools (R5), citations (R2), patient data (R7),
eligibility (R5), multi-step (R6), action (R9) and live ingest (R11).

## 2. Mandated Stack
| Layer | Required | Our choice |
|---|---|---|
| Orchestration | LangGraph StateGraph | LangGraph 1.x, Tier 1 fixed graph |
| API | FastAPI + Pydantic v2 | FastAPI 0.115+, Pydantic v2 |
| LLM | Not mandated | Groq (main), Gemini (fallback), MOCK_LLM for tests |
| Identity | Trusted request context | X-Patient-Id + X-Role headers |
| Storage | Structured + vector | SQLite (EMR/audit) + ChromaDB (policies) |
| Retrieval | Semantic search on approved docs | ChromaDB + MiniLM, active+effective filter |
| UI | Demo-ready | Streamlit |
| Deploy | Reproducible | docker-compose |

## 3. API Contract
### Endpoints
| Method | Path | Auth | Description |
|---|---|---|---|
| POST | /chat | X-Patient-Id, X-Role | Ask a question or perform an action |
| POST | /admin/ingest | X-Role: admin | Upload a new document |
| GET | /trace/{trace_id} | X-Patient-Id | Retrieve audit trace |
| GET | /health | none | Health check |

### Request Body (/chat)
```json
{"question": "string", "confirm": false}
```

### Response Body (/chat) — verbatim from spec
```json
{
  "trace_id": "HSP-93214",
  "answer": "Your MRI appointment is scheduled for 14 Oct 2026 at 10:30 AM.",
  "answer_type": "calculated",
  "citations": [{"system": "Hospital Scheduling System"}],
  "tools_invoked": [{"tool": "get_appointments"}],
  "explanation": "Retrieved from the patient appointment management system.",
  "assumptions": []
}
```

### answer_type enum (verbatim)
retrieved_fact | calculated | action_completed | clarification_needed | not_found | refused | conflict_flagged

### Fixed not-found message (verbatim)
"I could not find this information in the authorised hospital sources."

## 4. Traceability Matrix
| ID | Requirement | Component | Evidence | Stage | Status |
|---|---|---|---|---|---|
| R1 | Knowledge retrieval from approved docs | app/rag/index.py | test_search_tool.py | S2 | todo |
| R2 | Citations with source/section/version/date | app/graph/nodes.py:build_evidence | test_api_contract.py | S3 | todo |
| R3 | No hallucinations; not_found if unavailable | app/graph/nodes.py:output_guard | eval/cases.yaml | S4 | todo |
| R4 | Policy version/conflict resolution | app/graph/nodes.py:resolve | test_precedence.py | S3 | todo |
| R5 | Deterministic tools for eligibility/labs/etc | app/tools/hospital.py | test_tools.py | S3 | todo |
| R6 | Multi-step reasoning combining tools+docs | app/graph/nodes.py | eval/cases.yaml | S4 | todo |
| R7 | Authorization: identity from headers only | app/graph/nodes.py:input_guard | test_api_contract.py | S1 | todo |
| R8 | Uploaded docs treated as data | app/graph/nodes.py:input_guard | test_injection.py | S3 | todo |
| R9 | Answer classification in every response | app/api/schemas.py | test_api_contract.py | S1 | todo |
| R10 | Full audit trace per request | app/trace/store.py | test_api_contract.py | S1 | todo |
| R11 | Live document ingestion without restart | app/rag/ingest_docs.py, POST /admin/ingest | test_ingest.py | S2 | todo |

## 5. Data: SQLite Schema (synthetic, 20 rows each)
```sql
CREATE TABLE patients (patient_id TEXT PRIMARY KEY, full_name TEXT NOT NULL, date_of_birth TEXT, contact_number TEXT);
CREATE TABLE appointments (appointment_id TEXT PRIMARY KEY, patient_id TEXT, department TEXT, doctor_name TEXT,
  appointment_date TEXT, status TEXT, FOREIGN KEY(patient_id) REFERENCES patients(patient_id));
CREATE TABLE insurance_policies (policy_id TEXT PRIMARY KEY, patient_id TEXT, provider TEXT, plan_type TEXT,
  covered_procedures TEXT, status TEXT, FOREIGN KEY(patient_id) REFERENCES patients(patient_id));
CREATE TABLE lab_results (result_id TEXT PRIMARY KEY, patient_id TEXT, test_name TEXT, result_value TEXT,
  reference_range TEXT, date_tested TEXT, FOREIGN KEY(patient_id) REFERENCES patients(patient_id));
CREATE TABLE drug_interactions (interaction_id TEXT PRIMARY KEY, drug_a TEXT, drug_b TEXT, severity TEXT,
  clinical_action TEXT);
CREATE TABLE doctor_slots (slot_id TEXT PRIMARY KEY, doctor_name TEXT, department TEXT, slot_datetime TEXT,
  is_available INTEGER DEFAULT 1);
CREATE TABLE pending_actions (action_id TEXT PRIMARY KEY, patient_id TEXT, action_type TEXT, payload TEXT,
  created_at TEXT, expires_at TEXT, status TEXT DEFAULT 'pending');
CREATE TABLE audit_log (id INTEGER PRIMARY KEY AUTOINCREMENT, trace_id TEXT, patient_id TEXT,
  question_redacted TEXT, answer_type TEXT, tools_used TEXT, latency_ms REAL, model TEXT,
  error TEXT, created_at TEXT);
```

Edge cases:
- E1: Expired insurance → not_found/refused with expiry reason
- E2: No upcoming appointments → not_found
- E3: Pending lab (no result yet) → returned as pending, no value
- E4: Severe drug interaction → clearly flagged in response
- E5: Cross-patient request → refused, no info about target patient
- E6: Invalid reschedule date (past) → refused with reason + available slots
- E7: Condition not in hospital KB → not_found (verbatim message)
- E8: Policy conflict (tie) → picked by newest ingested

## 6. Rules Annex
- Conflict resolution: authority rank (government regulation > clinical guideline > hospital policy) > version descending > effective_date descending > ingested_at descending (newest ingested wins ties)
- Reschedule eligibility: date must be future, appointment must be Scheduled+owned by the caller, doctor must have an available slot on that date
- Insurance eligibility: policy status must be Active; procedure name must match covered_procedures (case-insensitive substring)
- Drug check: severity Severe → clinical_action returned; Moderate → returned with warning; Mild → returned
- Identity: patient_id ONLY from X-Patient-Id header; never trust question text for identity

## 7. Evaluation Minimums
| Category | Min cases | Case IDs |
|---|---|---|
| Policy fact (retrieved_fact) | 4 | C01-C04 |
| Deterministic tool (calculated) | 5 | C05-C09 |
| Action completed | 2 | C10-C11 |
| Clarification needed | 2 | C12-C13 |
| Not found | 3 | C14-C16 |
| Refused (cross-patient/injection) | 4 | C17-C20 |
| Conflict flagged | 1 | C21 |
| Multi-step | 2 | C22-C23 |
| Edge cases | 2+ | C24-C25 |

Metrics: answer_accuracy, citation_accuracy, tool_accuracy, refusal_accuracy, abstention_accuracy, retrieval_hit_rate, p50_latency_ms, p95_latency_ms

## 8. Scoring Rubric
| Criterion | What we must show |
|---|---|
| Answer accuracy | Correct answer type + content from tools/docs |
| Grounding | Every claim traceable to a citation or tool result |
| Privacy | Cross-patient requests refused; no PII in unauthenticated paths |
| Auditability | Trace ID, tools used, latency in every response |
| Live ingest | Upload a doc and ask about it without restart |
| Simplest architecture | One-graph, no unnecessary agents, clear rationale |
| Evaluation | 25+ cases, all metrics reported |

## 9. Disqualification Conditions
- Hard-coding a question string or expected answer → input_guard pattern check prevents special-casing
- Inventing medical facts → output_guard grounding check; not_found fallback
- Exposing another patient's data → input_guard + scoped SQL tools

## 10. Demo Must-Show List
1. ICU visiting hours → retrieved_fact with citation
2. Knee replacement coverage → calculated (eligibility tool)
3. Lab result query (HbA1c) → calculated
4. Cross-patient attempt → refused
5. Reschedule cardiology → action_completed (valid date) or refused (invalid date)
6. Unknown condition → not_found (exact message)
7. Admin uploads a new document → immediately queryable (R11)
8. Multi-step: pre-op readiness check

## 11. Deliverables
- README.md (run steps, architecture, assumptions)
- docs/DATA_CARD.md
- docs/AI_USAGE.md
- docs/CONTRIBUTIONS.md
- docs/DECLARATION.md
- docs/DEMO_SCRIPT.md
- docs/QA_CRIB.md
- eval/reports/ (latest run)
- docker-compose.yml (clean-clone runnable)

## 12. Schedule
- Event: HCLTech Future Ready AI Engineer Hackathon, 2026-10-24
- Stage 1: S1 skeleton + contract
- Stage 2: S2 DB seed + RAG seed + ingest
- Stage 3: S3 deterministic tools + tests
- Stage 4: S4 graph + LLM + guards
- Stage 5: S5 evaluation
- Stage 6: S6 UI + deliverables

## 13. Open Questions → Chosen Interpretations
- Q: JWT or headers? → X-Patient-Id + X-Role headers (JWT noted as production upgrade in README)
- Q: Two-step reschedule? → One-step: valid date → action_completed; invalid → refused; missing → clarification_needed
- Q: Conflict tie-break? → Newest ingested (ingest_at) wins; conflict_flagged kept for truly unresolvable ties (same doc different sections)
