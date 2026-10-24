"""
seed_docs.py — Seed the ChromaDB knowledge base with hospital policy documents.

Creates ~8 policy documents covering all demo scenarios:
  1. ICU Visiting Hours Policy (retrieved_fact test)
  2. MRI Scan Scheduling Procedure (procedure test)
  3. Pre-operative Protocol (multi-step test)
  4. Discharge Guidelines
  5. Insurance Agreement (general)
  6. Emergency Department Procedures
  7. Old ICU Policy v1.0 (superseded — tests version resolution R4)
  8. Infection Control Policy (tie-conflict document — same authority/version/date for E8)

Usage:
  python scripts/seed_docs.py
"""
from __future__ import annotations

from pathlib import Path

# All documents as inline text (no files needed for seeding)
DOCUMENTS = [
    {
        "name": "ICU Visiting Hours Policy",
        "authority": "hospital_policy",
        "version": "2.0",
        "effective_date": "2026-01-01",
        "section": "Visitor Management",
        "status": "active",
        "text": """
ICU Visiting Hours Policy — Version 2.0
Effective Date: 1 January 2026

Section 1: Visiting Hours
Visiting hours for ICU patients are strictly controlled to support patient recovery.

Permitted visiting hours:
- Morning session: 10:00 AM to 12:00 PM
- Evening session: 5:00 PM to 7:00 PM

Maximum 2 visitors are allowed at one time per ICU patient.
Children under 12 years of age are not permitted in the ICU.

Section 2: Visitor Requirements
All visitors must:
1. Register at the ICU nurse station upon arrival
2. Wash hands with hospital-grade antiseptic solution
3. Wear a hospital-provided gown if requested by nursing staff
4. Follow all infection control protocols as directed

Section 3: Exceptions
Exceptions to standard visiting hours may be granted for:
- End-of-life situations (24-hour visiting permitted with nurse approval)
- Paediatric patients (one parent may remain bedside at all times)
- Medical emergencies requiring family presence

For exceptions, contact the ICU Charge Nurse on duty.

Document Authority: Hospital Administration
Policy Owner: Director of Nursing
Review Date: January 2027
        """,
    },
    {
        "name": "MRI Scan Scheduling Procedure",
        "authority": "hospital_policy",
        "version": "1.5",
        "effective_date": "2026-03-01",
        "section": "Radiology Procedures",
        "status": "active",
        "text": """
MRI Scan Scheduling Procedure — Version 1.5
Effective Date: 1 March 2026

Section 1: Overview
This procedure outlines the approved steps for scheduling an MRI scan at this hospital.

Section 2: Scheduling Steps

Step 1: Obtain a referral
You must have a valid referral from your treating physician or specialist to schedule an MRI scan.
Self-referrals are not accepted. Contact your doctor to obtain a referral order.

Step 2: Contact Radiology Scheduling
Call the Radiology Scheduling Desk at extension 4567 or visit the Radiology Reception on Level 2.
You may also request scheduling through the patient portal.

Step 3: Insurance Pre-authorisation
If your insurance requires pre-authorisation for MRI scans, your doctor's office will obtain this
before scheduling. Confirm with your insurance provider whether pre-authorisation is needed.

Step 4: Preparation Instructions
You will receive specific preparation instructions before your MRI:
- Remove all metal jewellery and piercings
- Inform staff of any metal implants, pacemakers, or cochlear implants
- Fasting may be required for contrast-enhanced MRI (typically 4 hours)
- Wear comfortable, loose-fitting clothing without metal fastenings

Step 5: Arrival
Arrive 15 minutes before your scheduled appointment time.
Bring your referral, insurance card, and a valid photo ID.

Section 3: Rescheduling
To reschedule or cancel your MRI, contact Radiology Scheduling at least 24 hours in advance.

Document Authority: Hospital Administration
Department: Radiology
Review Date: March 2027
        """,
    },
    {
        "name": "Pre-operative Assessment Protocol",
        "authority": "clinical_guideline",
        "version": "3.1",
        "effective_date": "2026-02-01",
        "section": "Surgical Protocols",
        "status": "active",
        "text": """
Pre-operative Assessment Protocol — Version 3.1
Effective Date: 1 February 2026

Section 1: Purpose
This protocol defines the mandatory pre-operative assessments that must be completed
before any elective surgical procedure.

Section 2: Required Pre-operative Tests
All patients scheduled for elective surgery must have the following completed within
30 days of the surgical date:

Mandatory tests for all patients:
- Complete Blood Count (CBC)
- Basic Metabolic Panel (BMP) including creatinine and electrolytes
- Coagulation studies (PT/INR)
- Electrocardiogram (ECG) for patients over 40 years of age
- Chest X-Ray for patients over 60 years of age or with respiratory history

Additional tests based on procedure type:
- Cardiac surgery: Echocardiogram, Stress Test, Lipid Panel
- Orthopaedic surgery (knee/hip): X-Ray of affected joint, HbA1c if diabetic
- Abdominal surgery: Liver function tests, Abdominal ultrasound

Section 3: Pre-operative Clearance
A patient is cleared for surgery when:
1. All required tests have been completed and results are available
2. Insurance pre-authorisation has been obtained
3. Anaesthesiology pre-assessment is completed
4. Surgeon has reviewed all results and signed the clearance form

Section 4: Surgical Readiness Checklist
- [ ] Required lab tests ordered and resulted
- [ ] Insurance authorisation confirmed
- [ ] Surgeon availability confirmed
- [ ] Operating theatre booked
- [ ] Anaesthesiology review completed
- [ ] Patient consent obtained
- [ ] Medication review completed (hold anticoagulants as directed)

Document Authority: Clinical Governance Committee
Department: Surgery
Review Date: February 2027
        """,
    },
    {
        "name": "Patient Discharge Guidelines",
        "authority": "hospital_policy",
        "version": "2.2",
        "effective_date": "2026-01-15",
        "section": "Discharge Management",
        "status": "active",
        "text": """
Patient Discharge Guidelines — Version 2.2
Effective Date: 15 January 2026

Section 1: Discharge Process
The discharge process begins when the treating physician determines that the patient
is medically ready to leave the hospital.

Section 2: Discharge Preparation
On the day of discharge:
1. The nursing team will review discharge instructions with the patient
2. All medications will be reconciled and a medication list provided
3. Follow-up appointments will be scheduled before departure
4. The patient will receive written discharge instructions

Section 3: Discharge Instructions Content
Discharge instructions must include:
- Diagnosis and summary of hospital treatment
- Medications: new prescriptions, changes, and what to continue or stop
- Activity restrictions and wound care instructions if applicable
- Dietary recommendations
- Warning signs that require immediate medical attention
- Follow-up appointment details (who, when, where)
- Contact information for the care team

Section 4: Transport Requirements
Patients may not drive themselves home after:
- Any surgical procedure under general or spinal anaesthesia
- Administration of sedating medications
In these cases, a responsible adult must be present to escort the patient.

Section 5: Discharge Timing
Standard discharge time is before 11:00 AM to allow room preparation for incoming patients.
Late discharge requests must be approved by the ward charge nurse.

Document Authority: Hospital Administration
Department: Patient Services
Review Date: January 2027
        """,
    },
    {
        "name": "Hospital Insurance and Billing Policy",
        "authority": "hospital_policy",
        "version": "1.8",
        "effective_date": "2026-01-01",
        "section": "Billing and Finance",
        "status": "active",
        "text": """
Hospital Insurance and Billing Policy — Version 1.8
Effective Date: 1 January 2026

Section 1: Insurance Verification
The hospital verifies insurance eligibility before or at the time of admission.
Patients are responsible for confirming their insurance coverage for planned procedures.

Section 2: Covered Services
Insurance coverage varies by plan. Common covered services include:
- Inpatient hospitalisation (room and board)
- Surgical procedures listed in the insurance agreement
- Emergency care
- Diagnostic tests ordered by treating physicians
- Specialist consultations

Services that are typically NOT covered without special authorisation:
- Cosmetic procedures
- Experimental treatments
- Out-of-network specialist fees without referral

Section 3: Pre-authorisation Requirements
Many procedures require pre-authorisation from the insurance provider.
The hospital's Insurance Coordination team (extension 5678) can assist with this process.
Pre-authorisation must be obtained BEFORE the procedure is performed.

Section 4: Patient Billing Rights
Patients have the right to:
- Receive an itemised bill on request
- Be informed of estimated costs before elective procedures
- Apply for financial assistance if unable to pay
- Request a billing review if they believe charges are incorrect

Section 5: Contact
For billing enquiries, contact the Patient Financial Services desk on Level 1 or
call extension 5001 between 8:00 AM and 5:00 PM on weekdays.

Document Authority: Hospital Administration
Department: Finance and Billing
Review Date: January 2027
        """,
    },
    {
        "name": "Emergency Department Triage Protocol",
        "authority": "clinical_guideline",
        "version": "4.0",
        "effective_date": "2026-04-01",
        "section": "Emergency Procedures",
        "status": "active",
        "text": """
Emergency Department Triage Protocol — Version 4.0
Effective Date: 1 April 2026

Section 1: Triage Categories
The Emergency Department uses a 5-level triage system:

Level 1 — Resuscitation (Immediate): Life-threatening emergencies requiring immediate intervention.
Examples: Cardiac arrest, respiratory failure, severe trauma, unconsciousness.
Target time to treatment: Immediate.

Level 2 — Emergency (within 10 minutes): Conditions that are potentially life-threatening.
Examples: Chest pain, stroke symptoms, severe allergic reaction, high fever in infants.
Target time to treatment: 10 minutes.

Level 3 — Urgent (within 30 minutes): Serious conditions requiring prompt treatment.
Examples: Moderate pain, suspected fractures, vomiting with signs of dehydration.
Target time to treatment: 30 minutes.

Level 4 — Semi-urgent (within 60 minutes): Conditions that need treatment but are not immediately threatening.
Examples: Minor injuries, mild pain, urinary tract infections.
Target time to treatment: 60 minutes.

Level 5 — Non-urgent (within 120 minutes): Minor conditions with low risk.
Examples: Minor cuts, mild headache, chronic conditions requiring medication renewal.
Target time to treatment: 120 minutes.

Section 2: Arrival and Assessment
All patients arriving at the Emergency Department must report to the triage desk.
A registered triage nurse will assess the patient and assign a triage level.
Patients with Level 1 or 2 conditions will be taken directly to a treatment bay.

Document Authority: Clinical Governance Committee
Department: Emergency Medicine
Review Date: April 2027
        """,
    },
    {
        "name": "ICU Visiting Hours Policy (Superseded)",
        "authority": "hospital_policy",
        "version": "1.0",
        "effective_date": "2024-01-01",
        "section": "Visitor Management",
        "status": "superseded",   # This is the OLD version — should NOT be returned
        "text": """
ICU Visiting Hours Policy — Version 1.0 (SUPERSEDED)
Effective Date: 1 January 2024
Superseded by Version 2.0 effective 1 January 2026.

OLD HOURS: Morning 9:00 AM to 11:00 AM, Evening 4:00 PM to 6:00 PM.
Maximum 3 visitors at one time.
        """,
    },
    {
        "name": "Infection Control Standard",
        "authority": "clinical_guideline",
        "version": "2.0",
        "effective_date": "2026-01-01",
        "section": "Infection Prevention",
        "status": "active",
        "text": """
Infection Control Standard — Version 2.0
Effective Date: 1 January 2026

Section 1: Hand Hygiene
Hand hygiene is the single most effective way to prevent infection spread.
All staff, patients and visitors must perform hand hygiene:
- Before entering and after leaving a patient area
- Before and after any patient contact
- After contact with blood, body fluids or contaminated surfaces

Use alcohol-based hand rub (minimum 60% alcohol) or soap and water.
The WHO 6-step hand hygiene technique must be followed.

Section 2: Personal Protective Equipment (PPE)
PPE must be used as directed by the clinical team:
- Gloves: for contact with blood, body fluids, or non-intact skin
- Gowns: for procedures with risk of splash or when caring for patients on contact precautions
- Masks: surgical masks for droplet precautions; N95 respirators for airborne precautions
- Eye protection: for procedures with splash risk

Section 3: Isolation Precautions
Patients with known or suspected infectious conditions will be placed in appropriate isolation:
- Standard precautions: applied to ALL patients at ALL times
- Contact precautions: for MRSA, VRE, C. difficile
- Droplet precautions: for influenza, COVID-19
- Airborne precautions: for tuberculosis, measles (negative pressure room required)

Document Authority: Infection Control Committee
Department: Infection Prevention and Control
Review Date: January 2027
        """,
    },
]


def seed_all_documents() -> None:
    """Ingest all policy documents into ChromaDB."""
    # Inline import to allow running as a script
    import sys
    sys.path.insert(0, str(Path(__file__).parents[1]))

    from app.rag.ingest_docs import ingest_document
    import tempfile

    print("Seeding ChromaDB knowledge base...")
    total_chunks = 0

    for doc in DOCUMENTS:
        # Write text to a temp file, then ingest
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False, encoding="utf-8") as tmp:
            tmp.write(doc["text"])
            tmp_path = tmp.name

        # Override status in metadata by adding it to the ingest
        result = ingest_document(
            file_path=Path(tmp_path),
            doc_name=doc["name"],
            authority=doc["authority"],
            version=doc["version"],
            effective_date=doc["effective_date"],
            section=doc["section"],
        )

        # For superseded docs, update the status in ChromaDB
        if doc.get("status") == "superseded":
            _mark_superseded(result.get("doc_id", ""), doc["name"])

        Path(tmp_path).unlink()  # clean up temp file

        status = "OK" if result.get("success") else "FAIL"
        print(f"  [{status}] {doc['name']} v{doc['version']} ({result.get('chunks_added', 0)} chunks) [{doc.get('status', 'active')}]")
        total_chunks += result.get("chunks_added", 0)

    print(f"\nKnowledge base ready: {len(DOCUMENTS)} documents, {total_chunks} chunks total")


def _mark_superseded(doc_id: str, doc_name: str) -> None:
    """Update the status metadata of superseded document chunks."""
    try:
        from app.rag.index import _get_collection
        collection = _get_collection()
        # Get all chunks for this doc
        results = collection.get(where={"doc": doc_name}, include=["metadatas"])
        if results and results.get("ids"):
            for chunk_id, meta in zip(results["ids"], results["metadatas"]):
                meta["status"] = "superseded"
                collection.update(ids=[chunk_id], metadatas=[meta])
    except Exception as e:
        print(f"  Warning: could not mark superseded for {doc_name}: {e}")


if __name__ == "__main__":
    seed_all_documents()
