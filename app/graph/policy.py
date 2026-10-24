"""
policy.py — Problem-specific routing rules for the Hospital assistant.

The router node calls classify_intent() first (keyword rules, no LLM cost).
Only truly ambiguous questions fall through to the LLM router fallback.
All answer_type values, fixed messages, and entity patterns live here.
"""
from __future__ import annotations
import re
from app.api.schemas import NOT_FOUND_MSG  # noqa: F401 — re-export for convenience

# ---------------------------------------------------------------------------
# Intent labels — must match exactly the branch names in build.py
# ---------------------------------------------------------------------------
INTENT_POLICY_FACT    = "policy_fact"
INTENT_PROCEDURE      = "procedure"
INTENT_PERSONAL_DATA  = "personal_data"
INTENT_ELIGIBILITY    = "eligibility"
INTENT_LAB_RESULT     = "lab_result"
INTENT_DRUG_CHECK     = "drug_check"
INTENT_ACTION         = "action_request"
INTENT_OUT_OF_SCOPE   = "out_of_scope"
INTENT_MISSING_INFO   = "missing_info"

# ---------------------------------------------------------------------------
# Keyword trigger patterns (case-insensitive)
# Each tuple: (pattern, intent)
# First match wins — order matters (more specific first)
# ---------------------------------------------------------------------------
_KEYWORD_RULES: list[tuple[re.Pattern, str]] = [
    # Action requests
    (re.compile(r"\b(reschedule|rebook|change|move|cancel)\b.*\b(appointment|slot|booking)\b", re.I), INTENT_ACTION),
    (re.compile(r"\b(book|schedule|make)\b.*\b(appointment|slot)\b", re.I), INTENT_ACTION),
    (re.compile(r"\breschedule\b.*\bA\d{3,}\b", re.I), INTENT_ACTION),
    (re.compile(r"\bI want to (reschedule|cancel|change|move)\b", re.I), INTENT_ACTION),

    # Eligibility / insurance
    (re.compile(r"\b(covered|coverage|eligible|insurance|insur|copay|deductible|claim)\b", re.I), INTENT_ELIGIBILITY),
    (re.compile(r"\b(my plan|my policy|does my|will my)\b.*\b(cover|pay|reimburse)\b", re.I), INTENT_ELIGIBILITY),

    # Lab results
    (re.compile(r"\b(lab|laboratory|blood|test result|hba1c|glucose|cholesterol|creatinine|cbc|hemoglobin|biopsy|ecg)\b", re.I), INTENT_LAB_RESULT),
    (re.compile(r"\b(my (latest|last|recent) (test|result|reading|report))\b", re.I), INTENT_LAB_RESULT),
    (re.compile(r"\b(lab results?|test results?|blood (work|report))\b", re.I), INTENT_LAB_RESULT),
    (re.compile(r"\bwhat were my\b.*\b(results?|labs?|tests?)\b", re.I), INTENT_LAB_RESULT),

    # Drug interactions
    (re.compile(r"\b(drug|medication|medicine|interaction|interact|contraindic)\b", re.I), INTENT_DRUG_CHECK),
    (re.compile(r"\b(warfarin|aspirin|ibuprofen|metformin|lisinopril|atorvastatin)\b", re.I), INTENT_DRUG_CHECK),
    (re.compile(r"\b(between|mixing|combine|taking)\b.*\band\b", re.I), INTENT_DRUG_CHECK),

    # Personal data (appointments, records) — must come before broad policy_fact rules
    (re.compile(r"\b(my appointments?|upcoming appointments?|when is my|my schedule|my next)\b", re.I), INTENT_PERSONAL_DATA),
    (re.compile(r"\b(my record|my file|my history|discharge summary)\b", re.I), INTENT_PERSONAL_DATA),
    (re.compile(r"\b(show me|list|what are) (my|the) (appointments?|visits?|bookings?)\b", re.I), INTENT_PERSONAL_DATA),
    (re.compile(r"\bwhat (appointments?|visits?|bookings?) do I have\b", re.I), INTENT_PERSONAL_DATA),
    (re.compile(r"\bdo I have any (appointments?|visits?|bookings?)\b", re.I), INTENT_PERSONAL_DATA),
    (re.compile(r"\bwhen.*\bnext (visit|appointment|checkup)\b", re.I), INTENT_PERSONAL_DATA),

    # Procedures (how-to)
    (re.compile(r"\b(how (do|can|should) (i|we)|what (are the )?steps|procedure for|process (for|to))\b", re.I), INTENT_PROCEDURE),
    (re.compile(r"\bwhat happens (on|during|when|if|before|after)\b", re.I), INTENT_PROCEDURE),
    (re.compile(r"\bwhat (do i|should i) (do|bring|expect|prepare)\b", re.I), INTENT_PROCEDURE),
    (re.compile(r"\bhow (to|do i) (schedule|book|get|prepare|register)\b", re.I), INTENT_PROCEDURE),
    (re.compile(r"\b(discharge|discharged|day of discharge)\b", re.I), INTENT_PROCEDURE),
    (re.compile(r"\b(pre.?op|pre.?operative|before surgery|day of surgery)\b", re.I), INTENT_PROCEDURE),

    # Policy facts (visiting hours, policies, rules) — broad patterns last
    (re.compile(r"\b(visiting hours?|visit hours?|visitor policy|icu visit)\b", re.I), INTENT_POLICY_FACT),
    (re.compile(r"\b(policy|guideline|protocol|rule|regulation|standard)\b", re.I), INTENT_POLICY_FACT),
    (re.compile(r"\b(what (are|is) the (icu|visiting|discharge|triage|infection|hand|mri|pre.op|emergency))\b", re.I), INTENT_POLICY_FACT),
    (re.compile(r"\b(can i|am i allowed|is it allowed|am i permitted)\b", re.I), INTENT_POLICY_FACT),
    (re.compile(r"\b(visiting|triage|infection control|hand hygiene|emergency)\b", re.I), INTENT_POLICY_FACT),
    (re.compile(r"\b(tell me about|what is|explain|information about)\b", re.I), INTENT_POLICY_FACT),
]

# ---------------------------------------------------------------------------
# Injection / unsafe pattern detection (input_guard)
# ---------------------------------------------------------------------------
_INJECTION_PATTERNS: list[re.Pattern] = [
    re.compile(r"ignore (previous|all|prior|above) instruction", re.I),
    re.compile(r"bypass (verification|security|auth|guard)", re.I),
    re.compile(r"you are now|pretend (you are|to be)|act as", re.I),
    re.compile(r"</?(system|human|assistant|prompt)>", re.I),
    re.compile(r"execute (this|the following|command)", re.I),
    re.compile(r"jailbreak|disregard (safety|rules)", re.I),
]

# ---------------------------------------------------------------------------
# Cross-patient reference detection (input_guard R7)
# Pattern matches: patient IDs like P1002, names + "her/his records", etc.
# The check compares against the CALLER's patient_id — any other ID triggers refusal.
# ---------------------------------------------------------------------------
_OTHER_PATIENT_ID_PATTERN = re.compile(r"\bP\d{4}\b")  # e.g., P1002, P2005
_OTHER_PATIENT_NAME_PATTERN = re.compile(
    r"\b(her|his|their|another patient|someone else|my (daughter|son|wife|husband|friend|colleague))\b.*"
    r"(record|result|lab|appointment|data|file|schedule|insurance)",
    re.I,
)

# ---------------------------------------------------------------------------
# Authority rank for conflict resolution (R4)
# Higher number = higher authority
# ---------------------------------------------------------------------------
AUTHORITY_RANK: dict[str, int] = {
    "government_regulation": 3,
    "clinical_guideline": 2,
    "hospital_policy": 1,
}


# ---------------------------------------------------------------------------
# Public functions called by graph nodes
# ---------------------------------------------------------------------------

def classify_intent(question: str) -> str | None:
    """
    Keyword-first router. Returns an intent string or None (→ LLM fallback).

    Tries rules in order; first match wins. Returns None if nothing matches,
    which signals the router node to call the LLM for classification.
    """
    for pattern, intent in _KEYWORD_RULES:
        if pattern.search(question):
            return intent
    return None  # LLM fallback needed


def is_injection(question: str) -> bool:
    """Return True if the question contains a known injection pattern (R8)."""
    return any(p.search(question) for p in _INJECTION_PATTERNS)


def extract_other_patient_ids(question: str, caller_patient_id: str) -> list[str]:
    """
    Return any patient IDs mentioned in the question that are NOT the caller's (R7).
    Also returns a sentinel ['name_ref'] if indirect name references are found.
    """
    found = []
    # Explicit IDs like P1002
    for match in _OTHER_PATIENT_ID_PATTERN.finditer(question):
        pid = match.group()
        if pid != caller_patient_id:
            found.append(pid)
    # Indirect name references ("her records", "my daughter's test")
    if _OTHER_PATIENT_NAME_PATTERN.search(question):
        found.append("name_ref")
    return found


def authority_score(chunk: dict) -> tuple[int, str, str, str]:
    """
    Return a sort key for a policy chunk: (authority_rank, version, effective_date, ingested_at).
    Higher tuples are preferred. Used by the resolver for conflict resolution (R4).
    """
    auth = chunk.get("authority", "hospital_policy")
    rank = AUTHORITY_RANK.get(auth, 0)
    version = chunk.get("version", "0")
    effective_date = chunk.get("effective_date", "1900-01-01")
    ingested_at = chunk.get("ingested_at", "1900-01-01T00:00:00")
    return (rank, version, effective_date, ingested_at)
