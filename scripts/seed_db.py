"""
seed_db.py — Create and populate the hospital SQLite database with synthetic data.

Tables (from REQUIREMENTS.md schema):
  patients, appointments, insurance_policies, lab_results,
  drug_interactions, doctor_slots, pending_actions, audit_log

Designed to be idempotent: drops and recreates tables on every run.
Includes edge cases as required by the spec (E1-E8).

Usage:
  python scripts/seed_db.py
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parents[1] / "data" / "hospital.db"


def create_tables(conn: sqlite3.Connection) -> None:
    """Create all tables, dropping them first for a clean seed."""
    conn.executescript("""
    -- Drop existing tables (order matters for FK constraints)
    DROP TABLE IF EXISTS audit_log;
    DROP TABLE IF EXISTS pending_actions;
    DROP TABLE IF EXISTS doctor_slots;
    DROP TABLE IF EXISTS drug_interactions;
    DROP TABLE IF EXISTS lab_results;
    DROP TABLE IF EXISTS insurance_policies;
    DROP TABLE IF EXISTS appointments;
    DROP TABLE IF EXISTS patients;

    -- Patient demographics
    CREATE TABLE patients (
        patient_id      TEXT PRIMARY KEY,
        full_name       TEXT NOT NULL,
        date_of_birth   TEXT,
        contact_number  TEXT
    );

    -- Appointment schedule
    CREATE TABLE appointments (
        appointment_id   TEXT PRIMARY KEY,
        patient_id       TEXT,
        department       TEXT,
        doctor_name      TEXT,
        appointment_date TEXT,    -- ISO datetime "YYYY-MM-DD HH:MM"
        status           TEXT,    -- Scheduled | Completed | Cancelled
        FOREIGN KEY(patient_id) REFERENCES patients(patient_id)
    );

    -- Insurance policies
    CREATE TABLE insurance_policies (
        policy_id           TEXT PRIMARY KEY,
        patient_id          TEXT,
        provider            TEXT,
        plan_type           TEXT,
        covered_procedures  TEXT,  -- comma-separated list
        status              TEXT,  -- Active | Expired
        FOREIGN KEY(patient_id) REFERENCES patients(patient_id)
    );

    -- Lab / diagnostic results
    CREATE TABLE lab_results (
        result_id       TEXT PRIMARY KEY,
        patient_id      TEXT,
        test_name       TEXT,
        result_value    TEXT,   -- NULL = pending
        reference_range TEXT,
        date_tested     TEXT,
        FOREIGN KEY(patient_id) REFERENCES patients(patient_id)
    );

    -- Drug interaction knowledge base
    CREATE TABLE drug_interactions (
        interaction_id  TEXT PRIMARY KEY,
        drug_a          TEXT,
        drug_b          TEXT,
        severity        TEXT,   -- Mild | Moderate | Severe
        clinical_action TEXT
    );

    -- Doctor availability for scheduling
    CREATE TABLE doctor_slots (
        slot_id       TEXT PRIMARY KEY,
        doctor_name   TEXT,
        department    TEXT,
        slot_datetime TEXT,   -- ISO datetime
        is_available  INTEGER DEFAULT 1  -- 1=available, 0=booked
    );

    -- Pending multi-turn actions (not used in one-step MVP, reserved for future)
    CREATE TABLE pending_actions (
        action_id    TEXT PRIMARY KEY,
        patient_id   TEXT,
        action_type  TEXT,
        payload      TEXT,   -- JSON
        created_at   TEXT,
        expires_at   TEXT,
        status       TEXT DEFAULT 'pending'
    );

    -- Audit log (R10)
    CREATE TABLE audit_log (
        id                  INTEGER PRIMARY KEY AUTOINCREMENT,
        trace_id            TEXT,
        patient_id          TEXT,   -- masked as P****XXXX
        question_redacted   TEXT,
        answer_type         TEXT,
        tools_used          TEXT,
        latency_ms          REAL,
        model               TEXT,
        error               TEXT,
        created_at          TEXT
    );
    """)
    conn.commit()


def seed_patients(conn: sqlite3.Connection) -> None:
    """20 patients with realistic demographics."""
    patients = [
        ("P1001", "Alice Johnson",     "1985-03-14", "555-1001"),
        ("P1002", "Bob Martinez",      "1970-07-22", "555-1002"),
        ("P1003", "Carol Williams",    "1990-11-30", "555-1003"),
        ("P1004", "David Chen",        "1955-05-17", "555-1004"),
        ("P1005", "Emma Davis",        "2000-01-08", "555-1005"),
        ("P1006", "Frank Brown",       "1948-09-03", "555-1006"),
        ("P1007", "Grace Wilson",      "1978-12-20", "555-1007"),
        ("P1008", "Henry Taylor",      "1963-04-11", "555-1008"),
        ("P1009", "Isabella Anderson", "1995-06-25", "555-1009"),
        ("P1010", "James Thomas",      "1982-08-19", "555-1010"),
        ("P1011", "Karen Jackson",     "1940-02-28", "555-1011"),
        ("P1012", "Liam White",        "2005-10-15", "555-1012"),
        ("P1013", "Maria Harris",      "1967-03-07", "555-1013"),
        ("P1014", "Nathan Martin",     "1975-07-31", "555-1014"),
        ("P1015", "Olivia Thompson",   "1988-11-12", "555-1015"),
        ("P1016", "Paul Garcia",       "1952-04-22", "555-1016"),
        ("P1017", "Quinn Robinson",    "1993-09-14", "555-1017"),
        ("P1018", "Rachel Lee",        "1972-06-18", "555-1018"),
        ("P1019", "Samuel Walker",     "1960-01-29", "555-1019"),
        ("P1020", "Tina Hall",         "1998-08-03", "555-1020"),
    ]
    conn.executemany(
        "INSERT INTO patients VALUES (?, ?, ?, ?)", patients
    )


def seed_appointments(conn: sqlite3.Connection) -> None:
    """20 appointments including scheduled, completed, cancelled, and edge cases (E2)."""
    appointments = [
        # P1001 — has upcoming cardiology appointment (action test target)
        ("A001", "P1001", "Cardiology",    "Dr. Smith",    "2026-11-05 10:00", "Scheduled"),
        ("A002", "P1001", "Radiology",     "Dr. Patel",    "2026-10-20 09:30", "Completed"),  # past
        ("A003", "P1002", "Orthopedics",   "Dr. Brown",    "2026-11-10 14:00", "Scheduled"),
        ("A004", "P1003", "Neurology",     "Dr. Green",    "2026-11-15 11:00", "Scheduled"),
        ("A005", "P1004", "Oncology",      "Dr. Davis",    "2026-10-25 13:00", "Scheduled"),
        ("A006", "P1005", "Pediatrics",    "Dr. Kim",      "2026-10-28 09:00", "Scheduled"),
        ("A007", "P1006", "Cardiology",    "Dr. Smith",    "2026-11-20 10:30", "Scheduled"),
        ("A008", "P1007", "Ophthalmology", "Dr. Patel",    "2026-11-12 15:00", "Scheduled"),
        ("A009", "P1008", "Orthopedics",   "Dr. Brown",    "2026-10-15 08:00", "Completed"),  # past
        ("A010", "P1009", "Dermatology",   "Dr. White",    "2026-11-08 11:30", "Scheduled"),
        ("A011", "P1010", "Gastroenterol.","Dr. Sharma",   "2026-11-25 14:30", "Scheduled"),
        ("A012", "P1011", "Geriatrics",    "Dr. Johnson",  "2026-11-03 10:00", "Scheduled"),
        ("A013", "P1012", "Pediatrics",    "Dr. Kim",      "2026-10-30 09:30", "Cancelled"),  # cancelled
        ("A014", "P1013", "Urology",       "Dr. Adams",    "2026-11-18 13:00", "Scheduled"),
        ("A015", "P1014", "Neurology",     "Dr. Green",    "2026-11-07 11:00", "Scheduled"),
        ("A016", "P1015", "Endocrinology", "Dr. Patel",    "2026-11-14 10:00", "Scheduled"),
        ("A017", "P1016", "Pulmonology",   "Dr. Singh",    "2026-11-21 09:00", "Scheduled"),
        ("A018", "P1017", "Psychiatry",    "Dr. Moore",    "2026-11-09 14:00", "Scheduled"),
        ("A019", "P1018", "Rheumatology",  "Dr. Taylor",   "2026-11-16 15:30", "Scheduled"),
        # E2: P1020 has NO upcoming appointments (tests not_found for personal_data)
        ("A020", "P1020", "General",       "Dr. Williams", "2026-09-01 10:00", "Completed"),  # only past
    ]
    conn.executemany(
        "INSERT INTO appointments VALUES (?, ?, ?, ?, ?, ?)", appointments
    )


def seed_insurance(conn: sqlite3.Connection) -> None:
    """20 insurance policies including active, expired (E1), and various procedure coverage."""
    policies = [
        # P1001 — Gold plan covering Knee Replacement and MRI (eligibility test)
        ("INS001", "P1001", "HealthFirst",     "Gold",   "Knee Replacement, MRI Scan, CT Scan, Blood Tests, Cardiology Consultation", "Active"),
        # P1002 — Silver plan, no knee replacement (negative eligibility)
        ("INS002", "P1002", "BlueCare",        "Silver", "MRI Scan, X-Ray, Blood Tests, Emergency Care", "Active"),
        # P1003 — Active comprehensive
        ("INS003", "P1003", "MediShield",      "Platinum","Knee Replacement, Hip Replacement, MRI Scan, CT Scan, Surgery, Oncology, Chemotherapy", "Active"),
        # P1004 — Expired policy (E1)
        ("INS004", "P1004", "OldCare",         "Basic",  "Basic Consultations, Blood Tests", "Expired"),
        ("INS005", "P1005", "HealthFirst",     "Gold",   "Pediatric Care, Blood Tests, X-Ray, MRI Scan", "Active"),
        ("INS006", "P1006", "BlueCare",        "Silver", "Cardiology Consultation, MRI Scan, Blood Tests, ECG", "Active"),
        ("INS007", "P1007", "MediShield",      "Gold",   "Eye Surgery, Ophthalmology, MRI Scan, Blood Tests", "Active"),
        ("INS008", "P1008", "NationalHealth",  "Basic",  "Emergency Care, X-Ray, Basic Consultations", "Active"),
        ("INS009", "P1009", "SkinCare Plus",   "Gold",   "Dermatology, Skin Surgery, Blood Tests, MRI Scan", "Active"),
        ("INS010", "P1010", "HealthFirst",     "Silver", "Gastroenterology, Endoscopy, Blood Tests, CT Scan", "Active"),
        ("INS011", "P1011", "ElderCare",       "Platinum","Geriatric Care, Hip Replacement, Knee Replacement, Cardiac Surgery, Blood Tests", "Active"),
        # P1012 — No insurance at all (not in table)
        ("INS013", "P1013", "BlueCare",        "Gold",   "Urology, Kidney Surgery, Blood Tests, CT Scan, MRI Scan", "Active"),
        ("INS014", "P1014", "MediShield",      "Silver", "Neurology, Brain MRI, Blood Tests, EEG", "Active"),
        ("INS015", "P1015", "HealthFirst",     "Gold",   "Endocrinology, Diabetes Care, Blood Tests, HbA1c", "Active"),
        ("INS016", "P1016", "LungCare",        "Silver", "Pulmonology, Lung Function Test, CT Scan, Blood Tests", "Active"),
        ("INS017", "P1017", "MindHealth",      "Gold",   "Psychiatry, Mental Health, Blood Tests, Consultations", "Active"),
        ("INS018", "P1018", "RheumaCare",      "Silver", "Rheumatology, Joint Replacement, MRI Scan, Blood Tests", "Active"),
        ("INS019", "P1019", "BlueCare",        "Gold",   "Cardiology, Cardiac Surgery, Blood Tests, ECG, Stress Test", "Active"),
        ("INS020", "P1020", "HealthFirst",     "Basic",  "General Consultations, Blood Tests", "Active"),
        # Extra expired policy for P1001 (older plan)
        ("INS021", "P1001", "OldPlan",         "Basic",  "Basic Consultations", "Expired"),
    ]
    conn.executemany(
        "INSERT INTO insurance_policies VALUES (?, ?, ?, ?, ?, ?)", policies
    )


def seed_lab_results(conn: sqlite3.Connection) -> None:
    """20 lab results with various tests; includes pending result (E3) and abnormal values."""
    results = [
        # P1001 — HbA1c (lab test query target)
        ("L001", "P1001", "HbA1c",              "6.8%",     "Below 5.7% Normal, 5.7-6.4% Prediabetes, 6.5%+ Diabetes", "2026-10-01"),
        ("L002", "P1001", "Complete Blood Count","See report","WBC 4.5-11.0 K/uL, RBC 4.5-5.5 M/uL", "2026-09-15"),
        ("L003", "P1002", "Cholesterol Panel",   "LDL 145",  "LDL <100 mg/dL optimal", "2026-10-05"),
        ("L004", "P1003", "Tumor Marker CA-125", "35 U/mL",  "Normal <35 U/mL", "2026-10-10"),
        ("L005", "P1004", "PSA",                 "4.2 ng/mL","Normal <4.0 ng/mL", "2026-10-08"),
        ("L006", "P1005", "Complete Blood Count","WBC 8.5",  "WBC 4.5-11.0 K/uL", "2026-10-12"),
        ("L007", "P1006", "Troponin I",          "0.01 ng/mL","Normal <0.04 ng/mL", "2026-10-15"),
        ("L008", "P1007", "Intraocular Pressure","18 mmHg",  "Normal 10-21 mmHg", "2026-10-18"),
        ("L009", "P1008", "Creatinine",          "1.8 mg/dL","Normal 0.7-1.3 mg/dL", "2026-10-03"),  # elevated
        ("L010", "P1009", "Allergy Panel",       "Positive", "IgE elevated", "2026-10-20"),
        # E3: Pending lab result for P1010 (no result_value)
        ("L011", "P1010", "Colonoscopy Biopsy",  None,       "Pending pathology review", "2026-10-22"),
        ("L012", "P1011", "Bone Density (DEXA)", "-2.8 T",   "Osteoporosis <-2.5 T", "2026-09-28"),  # osteoporosis
        ("L013", "P1013", "Urinalysis",          "Normal",   "No abnormalities detected", "2026-10-19"),
        ("L014", "P1014", "Brain MRI Report",    "Reviewed", "No acute pathology", "2026-10-11"),
        ("L015", "P1015", "HbA1c",               "7.2%",     "Below 5.7% Normal, 5.7-6.4% Prediabetes, 6.5%+ Diabetes", "2026-10-17"),
        ("L016", "P1016", "Spirometry FEV1",     "68% pred", "Normal >80% predicted", "2026-10-14"),  # reduced
        ("L017", "P1017", "Thyroid TSH",         "2.1 mIU/L","Normal 0.4-4.0 mIU/L", "2026-10-09"),
        ("L018", "P1018", "CRP (Inflammation)",  "42 mg/L",  "Normal <10 mg/L", "2026-10-21"),  # elevated
        ("L019", "P1019", "Lipid Panel",         "LDL 178",  "LDL <100 mg/dL optimal", "2026-10-06"),
        ("L020", "P1020", "Blood Glucose",       "98 mg/dL", "Fasting normal 70-100 mg/dL", "2026-10-23"),
    ]
    conn.executemany(
        "INSERT INTO lab_results VALUES (?, ?, ?, ?, ?, ?)", results
    )


def seed_drug_interactions(conn: sqlite3.Connection) -> None:
    """20 drug interaction pairs including severe (E4), moderate, and mild cases."""
    interactions = [
        # Severe interactions (E4)
        ("DI001", "Warfarin",      "Aspirin",       "Severe",   "Avoid combination; significantly increases bleeding risk. Monitor INR closely."),
        ("DI002", "Methotrexate",  "NSAIDs",        "Severe",   "Avoid; NSAIDs reduce methotrexate excretion, risk of toxicity."),
        ("DI003", "MAO Inhibitors","Serotonin Drugs","Severe",   "Contraindicated; risk of serotonin syndrome."),
        ("DI004", "Warfarin",      "Ibuprofen",     "Severe",   "Avoid; increased bleeding risk. Use acetaminophen if needed."),
        ("DI005", "Digoxin",       "Amiodarone",    "Severe",   "Reduce digoxin dose by 50%; monitor levels and for toxicity."),
        # Moderate interactions
        ("DI006", "Metformin",     "Alcohol",       "Moderate", "Avoid excessive alcohol; risk of lactic acidosis."),
        ("DI007", "Statins",       "Amiodarone",    "Moderate", "Limit statin dose; increased risk of myopathy. Monitor CK levels."),
        ("DI008", "Clopidogrel",   "Omeprazole",    "Moderate", "Consider alternative PPI; omeprazole reduces clopidogrel efficacy."),
        ("DI009", "Lithium",       "Ibuprofen",     "Moderate", "NSAIDs can increase lithium levels; monitor closely."),
        ("DI010", "Tamoxifen",     "Paroxetine",    "Moderate", "Paroxetine reduces tamoxifen efficacy; consider alternative antidepressant."),
        ("DI011", "ACE Inhibitors","Potassium",     "Moderate", "Risk of hyperkalemia; monitor potassium levels."),
        ("DI012", "Metoprolol",    "Verapamil",     "Moderate", "Risk of bradycardia and heart block; monitor cardiac function."),
        # Mild interactions
        ("DI013", "Antacids",      "Tetracycline",  "Mild",     "Separate by 2 hours; antacids reduce tetracycline absorption."),
        ("DI014", "Caffeine",      "Ciprofloxacin", "Mild",     "Ciprofloxacin may increase caffeine effects; limit intake."),
        ("DI015", "Warfarin",      "Vitamin K",     "Mild",     "Consistent vitamin K intake; major changes may affect INR."),
        ("DI016", "Iron",          "Levothyroxine", "Mild",     "Separate by 4 hours; iron reduces levothyroxine absorption."),
        ("DI017", "Metformin",     "Contrast Dye",  "Moderate", "Hold metformin 48h before/after contrast procedures."),
        ("DI018", "Sildenafil",    "Nitrates",      "Severe",   "Contraindicated; can cause severe hypotension."),
        ("DI019", "Citalopram",    "Tramadol",      "Moderate", "Increased risk of serotonin syndrome and seizures."),
        ("DI020", "Amlodipine",    "Simvastatin",   "Moderate", "Limit simvastatin to 20mg/day; increased myopathy risk."),
    ]
    conn.executemany(
        "INSERT INTO drug_interactions VALUES (?, ?, ?, ?, ?)", interactions
    )


def seed_doctor_slots(conn: sqlite3.Connection) -> None:
    """Future appointment slots for reschedule operations."""
    slots = [
        ("SL001", "Dr. Smith",   "Cardiology",    "2026-11-14 09:00", 1),
        ("SL002", "Dr. Smith",   "Cardiology",    "2026-11-14 11:00", 1),
        ("SL003", "Dr. Smith",   "Cardiology",    "2026-11-16 10:00", 1),
        ("SL004", "Dr. Smith",   "Cardiology",    "2026-11-21 14:00", 1),
        ("SL005", "Dr. Patel",   "Radiology",     "2026-11-13 09:30", 1),
        ("SL006", "Dr. Patel",   "Radiology",     "2026-11-15 10:00", 1),
        ("SL007", "Dr. Patel",   "Radiology",     "2026-11-20 11:30", 1),
        ("SL008", "Dr. Brown",   "Orthopedics",   "2026-11-14 14:00", 1),
        ("SL009", "Dr. Brown",   "Orthopedics",   "2026-11-18 09:00", 1),
        ("SL010", "Dr. Green",   "Neurology",     "2026-11-12 10:00", 1),
        ("SL011", "Dr. Green",   "Neurology",     "2026-11-19 14:30", 1),
        ("SL012", "Dr. Kim",     "Pediatrics",    "2026-11-05 09:00", 1),
        ("SL013", "Dr. Kim",     "Pediatrics",    "2026-11-17 10:30", 1),
        ("SL014", "Dr. Davis",   "Oncology",      "2026-11-11 13:00", 1),
        ("SL015", "Dr. White",   "Dermatology",   "2026-11-10 11:00", 1),
        ("SL016", "Dr. Sharma",  "Gastroenterol.","2026-11-26 14:00", 1),
        ("SL017", "Dr. Johnson", "Geriatrics",    "2026-11-06 10:30", 1),
        ("SL018", "Dr. Adams",   "Urology",       "2026-11-19 13:30", 1),
        ("SL019", "Dr. Moore",   "Psychiatry",    "2026-11-11 15:00", 1),
        ("SL020", "Dr. Taylor",  "Rheumatology",  "2026-11-17 16:00", 1),
    ]
    conn.executemany(
        "INSERT INTO doctor_slots VALUES (?, ?, ?, ?, ?)", slots
    )


def main() -> None:
    """Create and seed the hospital database."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.execute("PRAGMA foreign_keys = ON")

    print(f"Seeding database at: {DB_PATH}")
    create_tables(conn)
    print("  [OK] Tables created")

    seed_patients(conn)
    print("  [OK] 20 patients")

    seed_appointments(conn)
    print("  [OK] 20 appointments")

    seed_insurance(conn)
    print("  [OK] 20 insurance policies")

    seed_lab_results(conn)
    print("  [OK] 20 lab results (including 1 pending)")

    seed_drug_interactions(conn)
    print("  [OK] 20 drug interactions (5 severe, 9 moderate, 6 mild)")

    seed_doctor_slots(conn)
    print("  [OK] 20 doctor slots")

    conn.commit()
    conn.close()
    print(f"\nDatabase ready at {DB_PATH}")


if __name__ == "__main__":
    main()
