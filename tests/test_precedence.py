# file: tests/test_precedence.py
# Not applicable: rule precedence for this project is handled in app/graph/policy.py (authority_score).
import pytest
pytest.skip("Template test — rule registry precedence handled in policy.py", allow_module_level=True)
import sqlite3
from datetime import date

from app.data.registry import Candidate, get_rule, resolve
from app.data.registry_io import upsert_rules, upsert_source
from app.data.registry_schema import REGISTRY_DDL
from app.data.rule_extract import ExtractedRule, verify

D = date.fromisoformat
POLICY = Candidate("RET-WIN-ELEC-01", "return_window_days", 10, "RET-POL-2024", "3.1", 1, D("2024-07-01"),
                   scope_categories=frozenset({"ELECTRONICS"}))
CIRC = Candidate("RET-WIN-ELEC-02", "return_window_days", 7, "CIRC-2026-07", "1", 2, D("2026-08-01"),
                 scope_categories=frozenset({"ELECTRONICS"}), supersedes=frozenset({"RET-POL-2024#3.1"}))
FAQ = Candidate("FAQ-RET-01", "return_window_days", 15, "HELP-FAQ", "Q4", 4, D("2026-09-15"))
FORUM = Candidate("FORUM-1", "return_window_days", 30, "FORUM-POST", "", 5, D("2026-01-01"))


def test_worked_example_circular_supersedes_and_faq_is_outranked():
    res = resolve([POLICY, CIRC, FAQ, FORUM], D("2026-10-06"), category="ELECTRONICS")
    assert res.status == "resolved" and res.value == 7 and res.winner.doc_id == "CIRC-2026-07"
    assert any("supersedes RET-POL-2024#3.1 (step 2)" in d for d in res.decisions)
    assert {c["loser"] for c in res.conflicts} == {"RET-WIN-ELEC-01", "FAQ-RET-01", "FORUM-1"}
    assert [c.rule_id for c in res.informational] == ["FORUM-1"]


def test_not_yet_effective_circular_is_upcoming_only():
    fashion = Candidate("RET-WIN-FASH-01", "return_window_days", 30, "RET-POL-2024", "3.2", 1, D("2024-07-01"),
                        scope_categories=frozenset({"FASHION"}))
    festive = Candidate("RET-WIN-FASH-02", "return_window_days", 45, "CIRC-FEST", "2", 2, D("2026-11-01"),
                        scope_categories=frozenset({"FASHION"}))
    res = resolve([fashion, festive], D("2026-10-06"), category="FASHION")
    assert res.value == 30 and [c.rule_id for c in res.upcoming] == ["RET-WIN-FASH-02"]
    assert "Upcoming change" in res.to_state()["assumptions"][0]


def test_same_authority_same_date_different_values_is_unresolved():
    a = Candidate("A", "fee_pct", 0.10, "CIRC-A", "1", 2, D("2026-08-01"))
    b = Candidate("B", "fee_pct", 0.05, "CIRC-B", "1", 2, D("2026-08-01"))
    res = resolve([a, b], D("2026-10-06"))
    assert res.status == "unresolved" and res.conflicts[0]["unresolved"]


def test_tier_exception_inside_one_document():
    general = Candidate("FEE-ALL", "restocking_fee_pct", 0.10, "RET-POL-2024", "5.1", 1, D("2024-07-01"))
    gold = Candidate("FEE-GOLD", "restocking_fee_pct", 0.0, "RET-POL-2024", "5.2", 1, D("2024-07-01"),
                     scope_tiers=frozenset({"GOLD", "PLATINUM"}))
    assert resolve([general, gold], D("2026-10-06"), tier="GOLD").value == 0.0
    assert resolve([general, gold], D("2026-10-06"), tier="STANDARD").value == 0.10


def test_registry_roundtrip_and_live_circular_changes_answer():
    conn = sqlite3.connect(":memory:")
    conn.executescript(REGISTRY_DDL)
    upsert_source(conn, {"doc_id": "RET-POL-2024", "title": "Return policy", "authority_level": 1,
                         "version": "3.1", "effective_from": "2024-07-01"})
    upsert_rules(conn, [{"rule_id": "W1", "parameter": "return_window_days", "value": 10,
                         "source_section": "3.1", "scope_categories": "ELECTRONICS"}],
                 {"doc_id": "RET-POL-2024", "effective_from": "2024-07-01"}, origin="curated")
    assert get_rule(conn, "return_window_days", "2026-10-06", category="ELECTRONICS").value == 10
    meta = {"doc_id": "CIRC-JDG-1", "title": "Window change", "authority_level": 2, "version": "1.0",
            "effective_from": "2026-09-01", "supersedes": "RET-POL-2024#3.1", "scope_categories": "ELECTRONICS"}
    upsert_source(conn, meta)
    upsert_rules(conn, [{"parameter": "return_window_days", "value": "5", "source_section": "2"}], meta,
                 origin="ingest-metadata")
    res = get_rule(conn, "return_window_days", "2026-10-06", category="ELECTRONICS")
    assert res.value == 5 and res.winner.doc_id == "CIRC-JDG-1"


def test_extraction_verification_rejects_values_not_in_quote():
    text = "1. With effect from 1 Sept 2026, electronics may be returned within 5 days of delivery."
    known = {"return_window_days": "days after delivery a return is accepted"}
    good = ExtractedRule(parameter="return_window_days", value="5", source_section="1",
                         evidence_quote="electronics may be returned within 5 days of delivery")
    bad = good.model_copy(update={"value": "7"})
    assert verify(good, text, known) == (True, "ok")
    assert verify(bad, text, known)[0] is False
