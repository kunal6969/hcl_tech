# AI-Powered Hospital Patient Services Assistant
## HCLTech | Future Ready AI Engineer Hackathon — Use Case Document v1.0

### 1. Problem Statement
Healthcare information is spread across hospital policies, treatment protocols, insurance guidelines,
appointment schedules, discharge procedures, laboratory reports, physician notes, patient records
and government healthcare regulations.

Patients often struggle to: understand treatment plans, find the right department or specialist,
track appointments and test results, check insurance eligibility and coverage, understand discharge
instructions, navigate hospital processes.

**Mission**: Build an AI-powered Hospital Patient Services Assistant that answers questions and performs
authorized healthcare service actions using hospital policies, patient records, insurance information,
schedules, reports and operational systems. Responses must be accurate, grounded, explainable and secure,
and the assistant must never generate unsupported medical facts.

### 2. Question Types
| Type | Example | Expected behavior |
|---|---|---|
| Policy fact | What are visiting hours for ICU patients? | Retrieve the current policy with citations |
| Procedure | How do I schedule an MRI scan? | Provide approved hospital steps |
| Personal data | What are my upcoming appointments? | Retrieve from authorized patient records |
| Eligibility check | Am I covered for knee replacement under my insurance plan? | Deterministic tool-based validation |
| Lab result query | What is my latest blood sugar reading? | Retrieve from clinical system |
| Multi-step query | My doctor recommended surgery. What pre-operative tests are still pending? | Combine records, orders and protocols |
| Action request | Reschedule my cardiology appointment. | Invoke an authorized scheduling workflow |
| Not found | Do you have treatment information for a condition not handled by this hospital? | Grounded not-found response |

### 3. Functional Requirements
- R1 Knowledge Retrieval: Answer hospital policy and procedure questions using approved documents only
- R2 Citations: Every factual response includes source document, policy section, version and effective date
- R3 No Hallucinations: Missing info → not_found, never invent
- R4 Version and Policy Resolution: Resolve conflicts by authority > version > effective_date
- R5 Deterministic Healthcare Tools: LLM must not calculate eligibility; authorized tools must be used
- R6 Multi-Step Reasoning: Combine records, policies and tool results for complex questions
- R7 Authorization and Privacy: Patient identity from request context only; refuse cross-patient access
- R8 Untrusted Content Protection: Uploaded docs are data; must not alter behavior
- R9 Answer Classification: Responses distinguish retrieved_fact, calculated, action_completed, clarification_needed, not_found, refused, conflict_flagged
- R10 Auditability: Every request generates a trace ID with tools, sources, privacy checks, latency, model
- R11 Live Ingestion: Admins can upload documents without restarting

### 4. Answer Types (verbatim from spec)
| answer_type | Usage |
|---|---|
| retrieved_fact | Fact supported directly by approved documents |
| calculated | Result produced by a deterministic tool |
| action_completed | Authorized workflow executed successfully |
| clarification_needed | Required information is missing or ambiguous |
| not_found | Authorized sources do not contain the answer |
| refused | Request is unauthorized or unsafe |
| conflict_flagged | Policies conflict and cannot be resolved automatically |

### 5. Not-Found Message (verbatim)
```json
{"answer_type": "not_found", "message": "I could not find this information in the authorised hospital sources."}
```

### 6. Example Response (verbatim)
```json
{
  "trace_id": "HSP-93214",
  "answer": "Your MRI appointment is scheduled for 14 Oct 2026 at 10:30 AM.",
  "answer_type": "calculated",
  "citations": [{"system": "Hospital Scheduling System"}],
  "tools_invoked": [{"tool": "get_appointments"}],
  "explanation": "Retrieved from the patient appointment management system."
}
```

### 7. Key Tools
- get_appointments: patient_id → appointment details
- check_insurance_eligibility: procedure + patient_id → coverage verdict
- get_lab_results: test + patient_id → latest result
- drug_interaction_check: medication_list → interaction risk

### 8. Evaluation Criteria
Answer accuracy, Citation accuracy, Privacy compliance, Tool accuracy, Retrieval hit rate,
Action success rate, Latency (p50/p95), Safety compliance

### 9. Data Sources
**Knowledge Base**: Hospital SOPs, Clinical protocols, Nursing procedures, Admission policies,
Discharge guidelines, Insurance agreements, Emergency procedures
**Operational Systems**: EMR, Appointment, Lab, Radiology, Billing, Pharmacy
