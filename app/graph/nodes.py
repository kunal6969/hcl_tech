"""
nodes.py — All LangGraph node functions for the Hospital assistant.

Each node is a plain Python function: (State) -> dict
The returned dict is a partial State update (only changed fields).

Node execution order (as wired in build.py):
  input_guard → router → [retrieve → resolve | tool_executor | action_workflow]
  → build_evidence → compose → output_guard → audit_writer → END

Terminal nodes (set answer + answer_type, skip to audit):
  refuse, clarify, not_found, conflict_flagged
"""
from __future__ import annotations

import time
import uuid
from typing import Any

from app.api.schemas import NOT_FOUND_MSG, ANSWER_TYPES
from app.graph.policy import (
    classify_intent,
    extract_other_patient_ids,
    is_injection,
    authority_score,
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
from app.graph.state import State
from app.llm.gateway import call_llm


# ---------------------------------------------------------------------------
# Node 1: input_guard  (R7, R8)
# ---------------------------------------------------------------------------

def input_guard(state: State) -> dict:
    """Deterministic safety check before any LLM call (R7, R8)."""
    question = state.get("question", "")
    caller_id = state.get("patient_id", "")
    trace_id = state.get("trace_id", "?")
    print(f"[NODE:input_guard] trace={trace_id} | patient={caller_id} | question={question[:60]!r}")

    if is_injection(question):
        print(f"[NODE:input_guard] BLOCKED — injection pattern detected")
        return {
            "answer": "I'm unable to process that request. Please ask a valid healthcare question.",
            "answer_type": "refused",
            "citations": [],
            "tools_invoked": [],
            "explanation": "Request blocked by content safety check.",
            "assumptions": [],
        }

    other_ids = extract_other_patient_ids(question, caller_id)
    if other_ids:
        print(f"[NODE:input_guard] BLOCKED — cross-patient reference: {other_ids}")
        return {
            "answer": "I can only provide information about your own records. I cannot access another patient's data.",
            "answer_type": "refused",
            "citations": [],
            "tools_invoked": [],
            "explanation": "Cross-patient access attempt detected and blocked (R7).",
            "assumptions": [],
        }

    print(f"[NODE:input_guard] PASSED — safe to continue")
    return {}


# ---------------------------------------------------------------------------
# Node 2: router
# ---------------------------------------------------------------------------

_ROUTER_SYSTEM_PROMPT = """You are a hospital patient services router. Classify the patient's question into exactly one intent.
You MUST be generous — if the question is even remotely related to healthcare, hospitals, patient services, or medical topics, it is NOT out_of_scope.

Intents (pick the BEST match — when in doubt, prefer policy_fact over out_of_scope):
- policy_fact: ANY question about hospital policies, rules, visiting hours, procedures, guidelines, regulations, departments, or general hospital information. This is the DEFAULT for any healthcare-related question.
- procedure: How to do something (steps to schedule, process to follow, what happens during discharge, pre-op, etc.)
- personal_data: Patient's own appointments, schedule, records, visits
- eligibility: Insurance coverage or cost for a procedure or treatment
- lab_result: Patient's test or laboratory results, blood work, reports
- drug_check: Drug interaction, medication safety, combining medicines
- action_request: Reschedule, book, cancel, or change an appointment (must mention a specific action)
- missing_info: Question is genuinely too vague to classify (e.g., just "help" with no context)
- out_of_scope: ONLY for questions completely unrelated to healthcare (e.g., "what's the weather", "who won the game", "write me a poem"). If there is ANY healthcare connection, do NOT use this.

Extract params (leave null if not present):
- procedure: procedure name (for eligibility)
- test: lab test name (for lab_result)
- medications: list of drug names (for drug_check)
- appointment_id: appointment ID like A001 (for action_request)
- preferred_date: date/datetime string (for action_request)

Return JSON only:
{"intent": "...", "params": {"procedure": null, "test": null, "medications": [], "appointment_id": null, "preferred_date": null}}
"""


def router(state: State) -> dict:
    """Classify intent and extract action parameters (keyword-first, LLM fallback)."""
    if state.get("answer_type") == "refused":
        print(f"[NODE:router] Skipping — already refused")
        return {}

    question = state.get("question", "")
    print(f"[NODE:router] Classifying: {question[:60]!r}")

    keyword_intent = classify_intent(question)
    print(f"[NODE:router] Keyword intent: {keyword_intent!r}")

    if keyword_intent and keyword_intent not in (INTENT_MISSING_INFO, INTENT_OUT_OF_SCOPE):
        params = _extract_params_only(question)
        print(f"[NODE:router] Using keyword intent={keyword_intent} | params={params}")
        return {"intent": keyword_intent, "params": params}

    print(f"[NODE:router] No keyword match — calling LLM for classification")
    llm_result = call_llm(
        system_prompt=_ROUTER_SYSTEM_PROMPT,
        user_message=question,
        mode="router",
    )
    intent = llm_result.get("intent", INTENT_OUT_OF_SCOPE)
    params = llm_result.get("params", {}) or {}
    print(f"[NODE:router] LLM intent={intent} | params={params}")
    return {"intent": intent, "params": params}


def _extract_params_only(question: str) -> dict:
    """
    Extract action parameters from a question whose intent is already known.
    First tries deterministic regex (no LLM cost), then falls back to LLM.
    This ensures MOCK_LLM=true still extracts procedure/test/appointment params.
    """
    import re as _re

    params: dict = {
        "procedure": None,
        "test": None,
        "medications": [],
        "appointment_id": None,
        "preferred_date": None,
    }

    # Appointment ID: A followed by digits (e.g. A001, A023)
    m = _re.search(r"\b(A\d{3,})\b", question)
    if m:
        params["appointment_id"] = m.group(1)

    # Preferred datetime: ISO date optionally followed by time
    m = _re.search(r"\b(\d{4}-\d{2}-\d{2})([ T]\d{2}:\d{2})?\b", question)
    if m:
        params["preferred_date"] = m.group(1) + (m.group(2) or "")

    # Known procedure names (case-insensitive substring match)
    _PROCEDURES = [
        "Knee Replacement", "Hip Replacement", "MRI Scan", "CT Scan",
        "X-Ray", "Ultrasound", "Colonoscopy", "Cardiac Surgery",
        "Echocardiogram", "Blood Test", "Basic Consultation", "Chemotherapy",
    ]
    q_lower = question.lower()
    for proc in _PROCEDURES:
        if proc.lower() in q_lower:
            params["procedure"] = proc
            break

    # Known lab tests
    _TESTS = [
        "HbA1c", "CBC", "Blood Glucose", "Cholesterol", "Creatinine",
        "Lipid Panel", "Liver Function", "Biopsy", "ECG",
    ]
    for test in _TESTS:
        if test.lower() in q_lower:
            params["test"] = test
            break

    # Medications: look for known drug names in a limited vocabulary
    _DRUGS = [
        "Warfarin", "Aspirin", "Metformin", "Lisinopril", "Atorvastatin",
        "Omeprazole", "Amoxicillin", "Ibuprofen", "Paracetamol", "Alcohol",
        "Clopidogrel", "Simvastatin", "Ramipril",
    ]
    params["medications"] = [d for d in _DRUGS if d.lower() in q_lower]

    # If we found meaningful params deterministically, use them
    if any([params["appointment_id"], params["preferred_date"], params["procedure"],
            params["test"], params["medications"]]):
        return params

    # Fall back to LLM for complex/unfamiliar parameter extraction
    prompt = (
        "Extract healthcare parameters from this question. "
        "Return JSON: "
        '{"procedure": null, "test": null, "medications": [], "appointment_id": null, "preferred_date": null}\n'
        f"Question: {question}"
    )
    result = call_llm(
        system_prompt="You are a parameter extractor. Return only JSON with the requested keys.",
        user_message=prompt,
        mode="router",
    )
    llm_params = result.get("params", result) if "params" in result else result
    # Merge LLM result into our defaults (LLM may fill what regex missed)
    if isinstance(llm_params, dict):
        for k, v in llm_params.items():
            if v and not params.get(k):
                params[k] = v
    return params


# ---------------------------------------------------------------------------
# Node 3: retrieve (ChromaDB search)
# ---------------------------------------------------------------------------

def retrieve(state: State) -> dict:
    """Semantic search on ChromaDB for policy / procedure documents (R1)."""
    if state.get("answer_type"):
        print(f"[NODE:retrieve] Skipping — answer already set: {state.get('answer_type')}")
        return {}

    from app.rag.index import search_documents

    question = state.get("question", "")
    intent = state.get("intent", "")
    print(f"[NODE:retrieve] Searching ChromaDB | intent={intent} | query={question[:60]!r}")

    chunks = search_documents(query=question, n_results=5, filters={"status": "active"})
    print(f"[NODE:retrieve] Found {len(chunks)} chunk(s) | docs={[c.get('doc','?') for c in chunks]}")
    return {"chunks": chunks}


# ---------------------------------------------------------------------------
# Node 4: resolve (conflict resolution, R4)
# ---------------------------------------------------------------------------

def resolve(state: State) -> dict:
    """Rank chunks by authority > version > effective_date. Flag conflicts if tied (R4)."""
    if state.get("answer_type"):
        print(f"[NODE:resolve] Skipping — answer already set: {state.get('answer_type')}")
        return {}

    chunks = state.get("chunks", [])
    print(f"[NODE:resolve] Ranking {len(chunks)} chunk(s)")

    if not chunks:
        print(f"[NODE:resolve] No chunks — returning not_found")
        return {
            "answer": NOT_FOUND_MSG,
            "answer_type": "not_found",
            "citations": [],
            "tools_invoked": [],
            "explanation": "No relevant documents found in the hospital knowledge base.",
            "assumptions": [],
        }

    ranked = sorted(chunks, key=authority_score, reverse=True)
    print(f"[NODE:resolve] Top chunk: {ranked[0].get('doc')!r} auth={ranked[0].get('authority')}")

    if len(ranked) >= 2:
        top1, top2 = ranked[0], ranked[1]
        same_rank = (
            authority_score(top1) == authority_score(top2)
            and top1.get("doc") != top2.get("doc")
        )
        if same_rank:
            print(f"[NODE:resolve] CONFLICT between {top1.get('doc')!r} and {top2.get('doc')!r}")
            return {
                "answer": (
                    "There are conflicting policies on this topic that I cannot automatically resolve. "
                    f"Please consult the hospital policy team. "
                    f"Sources: '{top1.get('doc')}' and '{top2.get('doc')}'."
                ),
                "answer_type": "conflict_flagged",
                "citations": [
                    {"doc": top1.get("doc"), "section": top1.get("section"), "version": top1.get("version")},
                    {"doc": top2.get("doc"), "section": top2.get("section"), "version": top2.get("version")},
                ],
                "tools_invoked": [],
                "explanation": "Two documents with equal authority, version and date disagree.",
                "assumptions": [],
            }

    print(f"[NODE:resolve] Resolved OK — {len(ranked)} ranked chunks")
    return {"chunks": ranked}


# ---------------------------------------------------------------------------
# Node 5: tool_executor (R5)
# ---------------------------------------------------------------------------

# Dispatch table: intent → tool function name
_TOOL_DISPATCH: dict[str, str] = {
    INTENT_PERSONAL_DATA: "get_appointments",
    INTENT_ELIGIBILITY:   "check_insurance_eligibility",
    INTENT_LAB_RESULT:    "get_lab_results",
    INTENT_DRUG_CHECK:    "drug_interaction_check",
}


def tool_executor(state: State) -> dict:
    """Call the deterministic SQL tool matching the router's intent (R5)."""
    if state.get("answer_type"):
        print(f"[NODE:tool_executor] Skipping — answer already set: {state.get('answer_type')}")
        return {}

    from app.tools.hospital import (
        get_appointments,
        check_insurance_eligibility,
        get_lab_results,
        drug_interaction_check,
    )

    intent = state.get("intent", "")
    params = state.get("params", {}) or {}
    patient_id = state["patient_id"]
    tool_name = _TOOL_DISPATCH.get(intent)
    print(f"[NODE:tool_executor] intent={intent} | tool={tool_name} | params={params}")

    if not tool_name:
        print(f"[NODE:tool_executor] No tool for intent={intent!r} — skipping")
        return {}

    tools_invoked: list[dict] = []
    result: dict[str, Any] = {}

    if tool_name == "get_appointments":
        print(f"[NODE:tool_executor] Calling get_appointments(patient_id={patient_id})")
        result = get_appointments(patient_id)

    elif tool_name == "check_insurance_eligibility":
        procedure = params.get("procedure") or ""
        print(f"[NODE:tool_executor] Calling check_insurance_eligibility | procedure={procedure!r}")
        if not procedure:
            print(f"[NODE:tool_executor] Missing procedure — clarification_needed")
            return {
                "answer": "Please specify the procedure you'd like to check coverage for.",
                "answer_type": "clarification_needed",
                "citations": [],
                "tools_invoked": [],
                "explanation": "Procedure name is required for insurance eligibility check.",
                "assumptions": [],
            }
        result = check_insurance_eligibility(patient_id, procedure)

    elif tool_name == "get_lab_results":
        test = params.get("test")
        print(f"[NODE:tool_executor] Calling get_lab_results | test={test!r}")
        result = get_lab_results(patient_id, test)

    elif tool_name == "drug_interaction_check":
        meds = params.get("medications") or []
        print(f"[NODE:tool_executor] Calling drug_interaction_check | meds={meds}")
        if len(meds) < 2:
            print(f"[NODE:tool_executor] Not enough meds ({len(meds)}) — clarification_needed")
            return {
                "answer": "Please provide at least two medication names to check for interactions.",
                "answer_type": "clarification_needed",
                "citations": [],
                "tools_invoked": [],
                "explanation": "Two or more medications required for drug interaction check.",
                "assumptions": [],
            }
        result = drug_interaction_check(meds)

    print(f"[NODE:tool_executor] Tool result: {str(result)[:120]}")
    tools_invoked.append({"tool": tool_name, "params": {"patient_id": "[redacted]"}, "result_summary": str(result)[:100]})
    return {"tool_results": [result], "tools_invoked": tools_invoked}


# ---------------------------------------------------------------------------
# Node 6: action_workflow (reschedule)
# ---------------------------------------------------------------------------

def action_workflow(state: State) -> dict:
    """Handle appointment reschedule: validate → update DB or refuse with alternatives."""
    if state.get("answer_type"):
        print(f"[NODE:action_workflow] Skipping — answer already set: {state.get('answer_type')}")
        return {}

    from app.tools.hospital import reschedule_appointment

    params = state.get("params", {}) or {}
    patient_id = state["patient_id"]
    appointment_id = params.get("appointment_id")
    preferred_date = params.get("preferred_date")
    print(f"[NODE:action_workflow] appointment_id={appointment_id!r} | preferred_date={preferred_date!r}")

    if not appointment_id or not preferred_date:
        missing = []
        if not appointment_id: missing.append("appointment ID")
        if not preferred_date: missing.append("preferred date and time")
        print(f"[NODE:action_workflow] Missing params: {missing} — clarification_needed")
        return {
            "answer": f"To reschedule your appointment, please provide: {', '.join(missing)}.",
            "answer_type": "clarification_needed",
            "citations": [],
            "tools_invoked": [],
            "explanation": "Required parameters missing for reschedule action.",
            "assumptions": [],
        }

    print(f"[NODE:action_workflow] Calling reschedule_appointment({patient_id}, {appointment_id}, {preferred_date})")
    result = reschedule_appointment(patient_id, appointment_id, preferred_date)
    print(f"[NODE:action_workflow] Result: {result}")
    tool_record = {"tool": "reschedule_appointment", "params": {"appointment_id": appointment_id}, "result_summary": str(result)[:100]}

    if result.get("success"):
        print(f"[NODE:action_workflow] Reschedule SUCCESS")
        return {"tool_results": [result], "tools_invoked": [tool_record]}
    else:
        slots = result.get("available_slots", [])
        slots_str = ", ".join(slots[:3]) if slots else "No slots currently available"
        print(f"[NODE:action_workflow] Reschedule FAILED: {result.get('reason')} | slots={slots[:3]}")
        return {
            "answer": (
                f"Unable to reschedule: {result.get('reason', 'Unknown error')}. "
                f"Available slots: {slots_str}."
            ),
            "answer_type": "refused",
            "citations": [],
            "tools_invoked": [tool_record],
            "explanation": result.get("reason", ""),
            "assumptions": [],
        }


# ---------------------------------------------------------------------------
# Node 7: build_evidence
# ---------------------------------------------------------------------------

def build_evidence(state: State) -> dict:
    """Compile chunks + tool results into a single grounded evidence packet (R6)."""
    if state.get("answer_type"):
        print(f"[NODE:build_evidence] Skipping — answer already set: {state.get('answer_type')}")
        return {}

    chunks = state.get("chunks", [])
    tool_results = state.get("tool_results", [])
    intent = state.get("intent", "")
    print(f"[NODE:build_evidence] chunks={len(chunks)} | tool_results={len(tool_results)} | intent={intent}")

    evidence: dict[str, Any] = {
        "intent": intent,
        "policy_chunks": [
            {
                "content": c.get("content", ""),
                "doc": c.get("doc", ""),
                "section": c.get("section", ""),
                "version": c.get("version", ""),
                "effective_date": c.get("effective_date", ""),
                "authority": c.get("authority", ""),
            }
            for c in chunks
        ],
        "tool_data": tool_results,
    }
    print(f"[NODE:build_evidence] Evidence built | policy_chunks={len(evidence['policy_chunks'])} | tool_data={len(evidence['tool_data'])}")
    return {"evidence": evidence}


# ---------------------------------------------------------------------------
# Node 8: compose (LLM answer generation)
# ---------------------------------------------------------------------------

_COMPOSE_SYSTEM_PROMPT = """You are a Hospital Patient Services Assistant.
Answer the patient's question STRICTLY using the Evidence Packet provided.

Rules:
1. ONLY use information from the Evidence Packet — never invent facts or medical information
2. Cite exact sources: document name, section, version, effective date
3. State any assumptions clearly
4. If the evidence is insufficient, say what you don't know
5. Be concise, clear, and empathetic
6. For tool data (appointments, lab results, etc.), present the data clearly

Return JSON:
{
  "answer": "your response",
  "explanation": "how you derived the answer",
  "assumptions": ["list of assumptions if any"]
}
"""


def compose(state: State) -> dict:
    """LLM node: generate grounded answer from evidence packet (R3, R6)."""
    if state.get("answer_type"):
        print(f"[NODE:compose] Skipping — answer already set: {state.get('answer_type')}")
        return {}

    evidence = state.get("evidence", {})
    question = state.get("question", "")
    intent = state.get("intent", "")
    print(f"[NODE:compose] Composing answer | intent={intent} | evidence_chunks={len(evidence.get('policy_chunks',[]))} | tool_data={len(evidence.get('tool_data',[]))}")

    user_message = f"Patient question: {question}\n\nEvidence Packet:\n{_format_evidence(evidence)}"

    result = call_llm(
        system_prompt=_COMPOSE_SYSTEM_PROMPT,
        user_message=user_message,
        mode="compose",
    )
    print(f"[NODE:compose] LLM answer preview: {str(result.get('answer',''))[:80]!r}")

    citations = []
    for chunk in evidence.get("policy_chunks", []):
        if chunk.get("doc"):
            citations.append({
                "doc": chunk["doc"],
                "section": chunk.get("section"),
                "version": chunk.get("version"),
                "effective_date": chunk.get("effective_date"),
            })
    for tool_data in evidence.get("tool_data", []):
        if isinstance(tool_data, dict) and tool_data.get("patient_id"):
            citations.append({"system": "Hospital Information System"})

    answer_type = _infer_answer_type(intent, evidence)
    print(f"[NODE:compose] answer_type={answer_type} | citations={len(citations)}")
    return {
        "answer": result.get("answer", NOT_FOUND_MSG),
        "answer_type": answer_type,
        "citations": citations,
        "explanation": result.get("explanation", ""),
        "assumptions": result.get("assumptions", []),
    }


def _format_evidence(evidence: dict) -> str:
    """Format the evidence packet as a readable string for the LLM."""
    parts = []
    for chunk in evidence.get("policy_chunks", []):
        parts.append(
            f"[Policy: {chunk.get('doc', 'Unknown')} | Section: {chunk.get('section')} | "
            f"Version: {chunk.get('version')} | Effective: {chunk.get('effective_date')}]\n"
            f"{chunk.get('content', '')}"
        )
    for item in evidence.get("tool_data", []):
        parts.append(f"[Tool Result: {item}]")
    return "\n---\n".join(parts) if parts else "No evidence available."


def _infer_answer_type(intent: str, evidence: dict) -> str:
    """Determine answer_type from intent and what data was found."""
    if evidence.get("tool_data"):
        if intent == INTENT_ACTION:
            return "action_completed"
        return "calculated"
    if evidence.get("policy_chunks"):
        if intent == INTENT_PROCEDURE:
            return "retrieved_fact"
        return "retrieved_fact"
    return "not_found"


# ---------------------------------------------------------------------------
# Node 9: output_guard
# ---------------------------------------------------------------------------

import re as _re
_PII_PATTERNS = [
    _re.compile(r"\b\d{10}\b"),                    # 10-digit phone numbers
    _re.compile(r"\b\d{4}-\d{2}-\d{2}\b"),         # dates of birth (same as ISO dates — be conservative)
    _re.compile(r"\b[A-Z]{2}\d{6,10}\b"),           # policy IDs (e.g., INS001234)
]


def output_guard(state: State) -> dict:
    """Final check: validate answer_type, mask PII before returning to client (R2, R3, R7)."""
    answer_type = state.get("answer_type", "")
    answer = state.get("answer", NOT_FOUND_MSG)
    print(f"[NODE:output_guard] answer_type={answer_type!r} | answer_preview={answer[:60]!r}")

    if not answer_type:
        print(f"[NODE:output_guard] No answer_type — routing to not_found")
        return {
            "answer": NOT_FOUND_MSG,
            "answer_type": "not_found",
            "citations": [],
            "explanation": "No answer was produced.",
            "assumptions": [],
        }

    if answer_type not in ANSWER_TYPES:
        print(f"[NODE:output_guard] Invalid answer_type {answer_type!r} — routing to not_found")
        return {
            "answer": NOT_FOUND_MSG,
            "answer_type": "not_found",
            "citations": [],
            "explanation": f"Internal error: invalid answer_type '{answer_type}'.",
            "assumptions": [],
        }

    pii_masked = 0
    for pattern in _PII_PATTERNS:
        new_answer, n = pattern.subn("[REDACTED]", answer)
        pii_masked += n
        answer = new_answer
    if pii_masked:
        print(f"[NODE:output_guard] Masked {pii_masked} PII pattern(s)")

    print(f"[NODE:output_guard] PASSED — returning answer_type={answer_type}")
    return {"answer": answer}


# ---------------------------------------------------------------------------
# Node 10: audit_writer (R10)
# ---------------------------------------------------------------------------

def audit_writer(state: State) -> dict:
    """Write completed trace to audit_log SQLite (R10)."""
    from app.trace.store import write_audit

    start = state.get("start_time", time.monotonic())
    latency_ms = (time.monotonic() - start) * 1000
    tools_used = ",".join(t.get("tool", "") for t in (state.get("tools_invoked") or []))
    answer_type = state.get("answer_type", "unknown")
    trace_id = state.get("trace_id", "unknown")

    print(f"[NODE:audit_writer] trace={trace_id} | answer_type={answer_type} | tools={tools_used!r} | latency={latency_ms:.0f}ms")

    question = state.get("question", "")
    question_redacted = _re.sub(r"\bP\d{4}\b", "[PATIENT_ID]", question)

    write_audit(
        trace_id=trace_id,
        patient_id=state.get("patient_id", "unknown"),
        question_redacted=question_redacted,
        answer_type=answer_type,
        tools_used=tools_used,
        latency_ms=latency_ms,
        model="MOCK" if not __import__("os").getenv("GROQ_API_KEY") else "groq",
        error=None,
    )
    print(f"[NODE:audit_writer] Audit written OK")
    return {"audit": {"latency_ms": round(latency_ms, 1), "tools_used": tools_used}}
