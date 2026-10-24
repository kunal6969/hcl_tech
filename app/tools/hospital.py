"""
hospital.py — Deterministic healthcare tools for the Hospital assistant (R5).

Every function here is:
  - Pure: same inputs → same outputs (given same DB state)
  - Scoped: SQL queries are always restricted to the caller's patient_id (R7)
  - Typed: inputs and outputs are plain dicts/lists for easy serialization
  - Commented: every function explains what it does and what it returns

The LLM never calls these directly; the tool_executor node dispatches to them
based on the intent extracted by the router.

Tools:
  get_appointments          → personal_data intent
  check_insurance_eligibility → eligibility intent
  get_lab_results           → lab_result intent
  drug_interaction_check    → drug_check intent
  reschedule_appointment    → action_request intent
"""
from __future__ import annotations

import sqlite3
from datetime import date, datetime
from pathlib import Path
from typing import Any

# Path to the SQLite database (created by scripts/seed_db.py)
_DB_PATH = Path(__file__).parents[2] / "data" / "hospital.db"


def _conn() -> sqlite3.Connection:
    """Open a read/write connection to the hospital database."""
    conn = sqlite3.connect(str(_DB_PATH))
    conn.row_factory = sqlite3.Row  # rows behave like dicts
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


# ---------------------------------------------------------------------------
# Tool 1: get_appointments
# ---------------------------------------------------------------------------

def get_appointments(patient_id: str) -> dict[str, Any]:
    """
    Retrieve upcoming and recent appointments for the authenticated patient.

    Args:
        patient_id: The caller's patient ID (from X-Patient-Id header, NOT the question).

    Returns:
        {
          "patient_id": "P1001",
          "appointments": [
            {"appointment_id": "A001", "department": "Cardiology",
             "doctor_name": "Dr. Smith", "appointment_date": "2026-11-01 10:00",
             "status": "Scheduled"}
          ],
          "count": 1
        }
    """
    with _conn() as conn:
        rows = conn.execute(
            """
            SELECT appointment_id, department, doctor_name, appointment_date, status
            FROM appointments
            WHERE patient_id = ?
            ORDER BY appointment_date
            """,
            (patient_id,),
        ).fetchall()

    appointments = [dict(r) for r in rows]
    return {
        "patient_id": patient_id,
        "appointments": appointments,
        "count": len(appointments),
    }


# ---------------------------------------------------------------------------
# Tool 2: check_insurance_eligibility
# ---------------------------------------------------------------------------

def check_insurance_eligibility(patient_id: str, procedure: str) -> dict[str, Any]:
    """
    Check whether the patient's active insurance covers a requested procedure.

    Uses case-insensitive substring matching against covered_procedures field.
    Expired policies are reported as not covered.

    Args:
        patient_id: The caller's patient ID.
        procedure: The procedure name, e.g. "Knee Replacement", "MRI Scan".

    Returns:
        {
          "patient_id": "P1001",
          "procedure": "Knee Replacement",
          "covered": true,
          "policy_id": "INS001",
          "provider": "HealthFirst",
          "plan_type": "Gold",
          "reason": "Procedure found in active policy coverage"
        }
    """
    with _conn() as conn:
        # Only check ACTIVE policies
        rows = conn.execute(
            """
            SELECT policy_id, provider, plan_type, covered_procedures, status
            FROM insurance_policies
            WHERE patient_id = ? AND status = 'Active'
            """,
            (patient_id,),
        ).fetchall()

    if not rows:
        # Check if patient has any policy (even expired) to give a better reason
        with _conn() as conn:
            has_policy = conn.execute(
                "SELECT 1 FROM insurance_policies WHERE patient_id = ?", (patient_id,)
            ).fetchone()
        reason = "No active insurance policy found" if not has_policy else "All insurance policies are expired"
        return {
            "patient_id": patient_id,
            "procedure": procedure,
            "covered": False,
            "policy_id": None,
            "provider": None,
            "plan_type": None,
            "reason": reason,
        }

    # Check each active policy for procedure coverage (case-insensitive substring)
    proc_lower = procedure.lower()
    for row in rows:
        covered_list = row["covered_procedures"] or ""
        # covered_procedures is stored as "Knee Replacement, MRI Scan, ..."
        if any(proc_lower in c.strip().lower() for c in covered_list.split(",")):
            return {
                "patient_id": patient_id,
                "procedure": procedure,
                "covered": True,
                "policy_id": row["policy_id"],
                "provider": row["provider"],
                "plan_type": row["plan_type"],
                "reason": "Procedure found in active policy coverage",
            }

    # Active policy exists but procedure not covered
    return {
        "patient_id": patient_id,
        "procedure": procedure,
        "covered": False,
        "policy_id": rows[0]["policy_id"],
        "provider": rows[0]["provider"],
        "plan_type": rows[0]["plan_type"],
        "reason": f"Procedure '{procedure}' is not listed in your active policy's covered procedures",
    }


# ---------------------------------------------------------------------------
# Tool 3: get_lab_results
# ---------------------------------------------------------------------------

def get_lab_results(patient_id: str, test_name: str | None = None) -> dict[str, Any]:
    """
    Retrieve lab results for the patient. Optionally filter by test name.

    Args:
        patient_id: The caller's patient ID.
        test_name: Optional test name filter, e.g. "HbA1c". If None, returns all tests.

    Returns:
        {
          "patient_id": "P1001",
          "test_name": "HbA1c",
          "results": [
            {"result_id": "L001", "test_name": "HbA1c", "result_value": "6.5%",
             "reference_range": "Below 5.7% Normal", "date_tested": "2026-10-01",
             "status": "completed"}
          ],
          "count": 1
        }
    """
    with _conn() as conn:
        if test_name:
            # Case-insensitive match on test name
            rows = conn.execute(
                """
                SELECT result_id, test_name, result_value, reference_range, date_tested
                FROM lab_results
                WHERE patient_id = ? AND LOWER(test_name) LIKE LOWER(?)
                ORDER BY date_tested DESC
                """,
                (patient_id, f"%{test_name}%"),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT result_id, test_name, result_value, reference_range, date_tested
                FROM lab_results
                WHERE patient_id = ?
                ORDER BY date_tested DESC
                """,
                (patient_id,),
            ).fetchall()

    results = [dict(r) for r in rows]
    # Mark pending results (no result_value)
    for r in results:
        r["status"] = "pending" if not r.get("result_value") else "completed"

    return {
        "patient_id": patient_id,
        "test_name": test_name or "all",
        "results": results,
        "count": len(results),
    }


# ---------------------------------------------------------------------------
# Tool 4: drug_interaction_check
# ---------------------------------------------------------------------------

def drug_interaction_check(medication_list: list[str]) -> dict[str, Any]:
    """
    Check pairwise drug interactions for a list of medications.

    Checks all pairs (A, B) and (B, A) against the drug_interactions table.

    Args:
        medication_list: List of drug names, e.g. ["Warfarin", "Aspirin"].

    Returns:
        {
          "medications_checked": ["Warfarin", "Aspirin"],
          "interactions": [
            {"drug_a": "Warfarin", "drug_b": "Aspirin",
             "severity": "Severe", "clinical_action": "Avoid combination; monitor INR closely"}
          ],
          "highest_severity": "Severe",
          "has_interactions": true
        }
    """
    if len(medication_list) < 2:
        return {
            "medications_checked": medication_list,
            "interactions": [],
            "highest_severity": None,
            "has_interactions": False,
            "note": "At least 2 medications needed for interaction check",
        }

    interactions = []
    with _conn() as conn:
        for i, drug_a in enumerate(medication_list):
            for drug_b in medication_list[i + 1:]:
                # Check both (A, B) and (B, A) orderings
                row = conn.execute(
                    """
                    SELECT drug_a, drug_b, severity, clinical_action
                    FROM drug_interactions
                    WHERE (LOWER(drug_a) = LOWER(?) AND LOWER(drug_b) = LOWER(?))
                       OR (LOWER(drug_a) = LOWER(?) AND LOWER(drug_b) = LOWER(?))
                    """,
                    (drug_a, drug_b, drug_b, drug_a),
                ).fetchone()
                if row:
                    interactions.append(dict(row))

    # Rank severity: Severe > Moderate > Mild
    severity_rank = {"Severe": 3, "Moderate": 2, "Mild": 1}
    highest = max(
        (i["severity"] for i in interactions),
        key=lambda s: severity_rank.get(s, 0),
        default=None,
    )

    return {
        "medications_checked": medication_list,
        "interactions": interactions,
        "highest_severity": highest,
        "has_interactions": len(interactions) > 0,
    }


# ---------------------------------------------------------------------------
# Tool 5: reschedule_appointment
# ---------------------------------------------------------------------------

def reschedule_appointment(
    patient_id: str,
    appointment_id: str,
    new_datetime: str,
) -> dict[str, Any]:
    """
    Reschedule an appointment to a new date/time (one-step; valid → done immediately).

    Eligibility checks (all deterministic):
      1. The appointment belongs to patient_id and has status 'Scheduled'
      2. new_datetime is in the future
      3. The doctor has an available slot on that date

    Args:
        patient_id: The caller's patient ID.
        appointment_id: The appointment to reschedule.
        new_datetime: ISO datetime string, e.g. "2026-11-15 14:00".

    Returns:
        {
          "success": true,
          "appointment_id": "A001",
          "new_datetime": "2026-11-15 14:00",
          "doctor_name": "Dr. Smith",
          "department": "Cardiology",
          "reason": "Appointment rescheduled successfully"
        }
        OR
        {
          "success": false,
          "reason": "Date is in the past",
          "available_slots": ["2026-11-14 09:00", "2026-11-16 14:00"]
        }
    """
    # --- Check 1: date is in the future ---
    try:
        new_dt = datetime.strptime(new_datetime, "%Y-%m-%d %H:%M")
    except ValueError:
        try:
            new_dt = datetime.fromisoformat(new_datetime)
        except ValueError:
            return {"success": False, "reason": f"Invalid date format: '{new_datetime}'. Use YYYY-MM-DD HH:MM"}

    if new_dt.date() <= date.today():
        available = _get_available_slots(None)
        return {
            "success": False,
            "reason": f"Requested date {new_datetime} is in the past or today. Please choose a future date.",
            "available_slots": available,
        }

    with _conn() as conn:
        # --- Check 2: appointment exists, belongs to caller, and is Scheduled ---
        appt = conn.execute(
            """
            SELECT appointment_id, patient_id, department, doctor_name, status
            FROM appointments
            WHERE appointment_id = ? AND patient_id = ?
            """,
            (appointment_id, patient_id),
        ).fetchone()

        if not appt:
            return {
                "success": False,
                "reason": "Appointment not found or does not belong to your account",
                "available_slots": [],
            }

        if appt["status"] != "Scheduled":
            return {
                "success": False,
                "reason": f"Appointment cannot be rescheduled (current status: {appt['status']})",
                "available_slots": [],
            }

        # --- Check 3: doctor has an available slot ---
        doctor = appt["doctor_name"]
        date_str = new_dt.strftime("%Y-%m-%d")
        slot = conn.execute(
            """
            SELECT slot_id, slot_datetime FROM doctor_slots
            WHERE doctor_name = ? AND DATE(slot_datetime) = ? AND is_available = 1
            ORDER BY slot_datetime
            LIMIT 1
            """,
            (doctor, date_str),
        ).fetchone()

        if not slot:
            available = _get_available_slots(doctor)
            return {
                "success": False,
                "reason": f"No available slot found for {doctor} on {date_str}",
                "available_slots": available,
            }

        # --- All checks passed: perform the reschedule ---
        conn.execute(
            "UPDATE appointments SET appointment_date = ?, status = 'Scheduled' WHERE appointment_id = ?",
            (new_datetime, appointment_id),
        )
        conn.execute(
            "UPDATE doctor_slots SET is_available = 0 WHERE slot_id = ?",
            (slot["slot_id"],),
        )
        conn.commit()

    return {
        "success": True,
        "appointment_id": appointment_id,
        "new_datetime": new_datetime,
        "doctor_name": appt["doctor_name"],
        "department": appt["department"],
        "reason": "Appointment rescheduled successfully",
    }


def _get_available_slots(doctor_name: str | None, limit: int = 5) -> list[str]:
    """Helper: get next available slots for a doctor (or any doctor if None)."""
    with _conn() as conn:
        if doctor_name:
            rows = conn.execute(
                """
                SELECT slot_datetime FROM doctor_slots
                WHERE doctor_name = ? AND is_available = 1 AND DATE(slot_datetime) > DATE('now')
                ORDER BY slot_datetime LIMIT ?
                """,
                (doctor_name, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT slot_datetime FROM doctor_slots
                WHERE is_available = 1 AND DATE(slot_datetime) > DATE('now')
                ORDER BY slot_datetime LIMIT ?
                """,
                (limit,),
            ).fetchall()
    return [r["slot_datetime"] for r in rows]
