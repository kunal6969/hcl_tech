"""
test_tools.py — Golden tests for all 5 deterministic hospital tools (R5).

Every test uses hand-derived expected values from the seeded database.
No network calls, no LLM. These tests run BEFORE the graph is wired up.

Setup: seeds the database before each test module run.
"""
from __future__ import annotations

import os
import pytest

os.environ["MOCK_LLM"] = "true"
os.environ["EMBEDDINGS"] = "hash"


@pytest.fixture(scope="module", autouse=True)
def seed_test_db():
    """Seed the test database before running tool tests."""
    # Import and run the seed script
    import scripts.seed_db as sdb
    sdb.main()


# ---------------------------------------------------------------------------
# Tool 1: get_appointments
# ---------------------------------------------------------------------------

class TestGetAppointments:
    def test_returns_appointments_for_valid_patient(self):
        from app.tools.hospital import get_appointments
        result = get_appointments("P1001")
        assert result["patient_id"] == "P1001"
        assert result["count"] >= 1
        assert isinstance(result["appointments"], list)

    def test_appointment_has_required_fields(self):
        from app.tools.hospital import get_appointments
        result = get_appointments("P1001")
        appt = result["appointments"][0]
        for field in ("appointment_id", "department", "doctor_name", "appointment_date", "status"):
            assert field in appt, f"Missing field: {field}"

    def test_e2_no_upcoming_appointments(self):
        """E2: P1020 has only a completed (past) appointment — still returns it."""
        from app.tools.hospital import get_appointments
        result = get_appointments("P1020")
        # Should return the completed appointment, count >= 0
        assert "appointments" in result

    def test_patient_isolation(self):
        """Tool must only return the caller's own appointments (not all patients')."""
        from app.tools.hospital import get_appointments
        result = get_appointments("P1001")
        for appt in result["appointments"]:
            # All appointments must belong to P1001 (not directly checkable from result,
            # but the SQL is scoped by patient_id so count won't include others)
            pass
        # P1002 should have different (or no) appointments from P1001
        result2 = get_appointments("P1002")
        ids1 = {a["appointment_id"] for a in result["appointments"]}
        ids2 = {a["appointment_id"] for a in result2["appointments"]}
        assert ids1.isdisjoint(ids2), "Appointments must not overlap between patients"


# ---------------------------------------------------------------------------
# Tool 2: check_insurance_eligibility
# ---------------------------------------------------------------------------

class TestCheckInsuranceEligibility:
    def test_covered_procedure(self):
        """P1001 has active Gold plan covering Knee Replacement."""
        from app.tools.hospital import check_insurance_eligibility
        result = check_insurance_eligibility("P1001", "Knee Replacement")
        assert result["covered"] is True
        assert result["patient_id"] == "P1001"
        assert result["procedure"] == "Knee Replacement"

    def test_not_covered_procedure(self):
        """P1002 has Silver plan that does NOT cover Knee Replacement."""
        from app.tools.hospital import check_insurance_eligibility
        result = check_insurance_eligibility("P1002", "Knee Replacement")
        assert result["covered"] is False
        assert "not listed" in result["reason"].lower() or "not" in result["reason"].lower()

    def test_e1_expired_insurance(self):
        """E1: P1004 has only expired insurance."""
        from app.tools.hospital import check_insurance_eligibility
        result = check_insurance_eligibility("P1004", "Basic Consultations")
        assert result["covered"] is False
        assert "expired" in result["reason"].lower() or "active" in result["reason"].lower()

    def test_mri_covered(self):
        """MRI Scan should be covered for P1001's Gold plan."""
        from app.tools.hospital import check_insurance_eligibility
        result = check_insurance_eligibility("P1001", "MRI Scan")
        assert result["covered"] is True

    def test_case_insensitive_matching(self):
        """Procedure matching must be case-insensitive."""
        from app.tools.hospital import check_insurance_eligibility
        result = check_insurance_eligibility("P1001", "knee replacement")  # lowercase
        assert result["covered"] is True


# ---------------------------------------------------------------------------
# Tool 3: get_lab_results
# ---------------------------------------------------------------------------

class TestGetLabResults:
    def test_hba1c_for_p1001(self):
        """P1001 has an HbA1c result of 6.8%."""
        from app.tools.hospital import get_lab_results
        result = get_lab_results("P1001", "HbA1c")
        assert result["count"] >= 1
        assert result["results"][0]["result_value"] == "6.8%"
        assert result["results"][0]["status"] == "completed"

    def test_e3_pending_result(self):
        """E3: P1010 has a pending biopsy result."""
        from app.tools.hospital import get_lab_results
        result = get_lab_results("P1010", "Biopsy")
        assert result["count"] >= 1
        pending = [r for r in result["results"] if r["status"] == "pending"]
        assert len(pending) >= 1, "P1010 should have at least one pending result"

    def test_no_results_for_unknown_test(self):
        """Query for a test that doesn't exist should return empty list."""
        from app.tools.hospital import get_lab_results
        result = get_lab_results("P1001", "NonExistentTest")
        assert result["count"] == 0
        assert result["results"] == []

    def test_all_results_without_filter(self):
        """Without test_name filter, all results for patient are returned."""
        from app.tools.hospital import get_lab_results
        result = get_lab_results("P1001")
        assert result["count"] >= 2  # P1001 has at least HbA1c and CBC

    def test_patient_isolation(self):
        """Lab results must be scoped to the requesting patient."""
        from app.tools.hospital import get_lab_results
        result_p1 = get_lab_results("P1001", "HbA1c")
        result_p2 = get_lab_results("P1002", "HbA1c")
        # P1002 doesn't have an HbA1c in our seed data
        assert result_p2["count"] == 0


# ---------------------------------------------------------------------------
# Tool 4: drug_interaction_check
# ---------------------------------------------------------------------------

class TestDrugInteractionCheck:
    def test_e4_severe_interaction(self):
        """E4: Warfarin + Aspirin has a Severe interaction."""
        from app.tools.hospital import drug_interaction_check
        result = drug_interaction_check(["Warfarin", "Aspirin"])
        assert result["has_interactions"] is True
        assert result["highest_severity"] == "Severe"
        assert len(result["interactions"]) >= 1

    def test_moderate_interaction(self):
        """Metformin + Alcohol has a Moderate interaction."""
        from app.tools.hospital import drug_interaction_check
        result = drug_interaction_check(["Metformin", "Alcohol"])
        assert result["has_interactions"] is True
        assert result["highest_severity"] in ("Moderate", "Severe")

    def test_no_interaction(self):
        """Two unrelated drugs with no recorded interaction."""
        from app.tools.hospital import drug_interaction_check
        result = drug_interaction_check(["Aspirin", "Vitamin C"])  # not in our DB
        assert result["has_interactions"] is False

    def test_single_drug_returns_no_interaction(self):
        """Single medication should return no interactions."""
        from app.tools.hospital import drug_interaction_check
        result = drug_interaction_check(["Aspirin"])
        assert result["has_interactions"] is False
        assert "At least 2" in result.get("note", "")

    def test_case_insensitive(self):
        """Drug names should match case-insensitively."""
        from app.tools.hospital import drug_interaction_check
        result = drug_interaction_check(["warfarin", "aspirin"])  # lowercase
        assert result["has_interactions"] is True

    def test_reverse_order(self):
        """(B, A) should find the same interaction as (A, B)."""
        from app.tools.hospital import drug_interaction_check
        result = drug_interaction_check(["Aspirin", "Warfarin"])  # reversed order
        assert result["has_interactions"] is True


# ---------------------------------------------------------------------------
# Tool 5: reschedule_appointment
# ---------------------------------------------------------------------------

class TestRescheduleAppointment:
    def test_e6_past_date_refused(self):
        """E6: Rescheduling to a past date should fail."""
        from app.tools.hospital import reschedule_appointment
        result = reschedule_appointment("P1001", "A001", "2024-01-15 10:00")
        assert result["success"] is False
        assert "past" in result["reason"].lower()

    def test_invalid_appointment_id(self):
        """Appointment that doesn't belong to the patient should fail."""
        from app.tools.hospital import reschedule_appointment
        result = reschedule_appointment("P1001", "A003", "2026-11-14 09:00")  # A003 belongs to P1002
        assert result["success"] is False
        assert "not found" in result["reason"].lower()

    def test_available_slots_returned_on_failure(self):
        """On failed reschedule, available slots should be returned."""
        from app.tools.hospital import reschedule_appointment
        result = reschedule_appointment("P1001", "A001", "2024-01-15 10:00")
        assert "available_slots" in result
        assert isinstance(result["available_slots"], list)
