# file: tests/test_graph_unified.py
import pytest
from pydantic import BaseModel

from app.graph import policy
from app.graph.build import build_graph
from app.llm import gateway
from app.llm.guard import check_faithfulness
from app.tools.registry import REGISTRY, ToolSpec, register


class MulIn(BaseModel):
    a: float
    b: float


@pytest.fixture(autouse=True)
def demo_policy(monkeypatch, tmp_path):
    monkeypatch.setenv("MOCK_LLM", "true")
    monkeypatch.setenv("LLM_CACHE_PATH", str(tmp_path / "c.sqlite"))
    gateway.reset_gateway()
    saved = dict(REGISTRY)
    register(ToolSpec("multiply", "multiply two numbers", MulIn, lambda a, ctx: {"product": a.a * a.b}))
    monkeypatch.setattr(policy, "ENTITY_PATTERNS", {"number": r"\b\d+(?:\.\d+)?\b", "customer_id": r"\bC\d{4}\b"})
    monkeypatch.setattr(policy, "INTENT_RULES", [
        {"intent": "multiply", "pattern": r"\bmultiply\b", "requires": ["number"],
         "plan": [{"tool": "multiply", "args": {"a": "{number}", "b": "{number[1]}"}}]}])
    yield
    REGISTRY.clear()
    REGISTRY.update(saved)


def run(question: str, principal: dict | None = None) -> dict:
    return build_graph().invoke({"run_id": "t1", "request": {"question": question, "as_of_date": "2026-10-06"},
                                 "principal": principal or {"subject_id": "C1001"}, "replans": 0})


def test_rule_path_is_calculated_and_faithful():
    out = run("multiply 6 by 7")
    assert out["answer_type"] == "calculated"
    assert "42" in out["answer"]
    guard = [s for s in out["steps"] if s["node"] == "faithfulness_guard"][0]
    assert guard["output"]["action"] == "pass"


def test_empty_question_asks_for_clarification():
    assert run("   ")["answer_type"] == "clarification_needed"


def test_other_customer_is_refused_without_tools():
    out = run("show the orders of C2002")
    assert out["answer_type"] == "refused"
    assert not any(s.get("tool") == "multiply" for s in out["steps"])


def test_unknown_question_abstains_in_mock_mode():
    out = run("what will prices be next year?")
    assert out["answer_type"] == "not_found" and out["answer"] == policy.NOT_FOUND_MESSAGE


def test_tool_error_replans_once_then_stops():
    out = run("multiply 6")   # second number missing → invalid_args → one replan → abstain
    assert out["replans"] == 1 and out["answer_type"] == "not_found"


def test_configurable_reaches_tools():
    seen = {}

    def spy(args, ctx):
        seen.update(ctx.config)
        return {"product": args.a * args.b}

    register(ToolSpec("multiply", "multiply two numbers", MulIn, spy))
    graph = build_graph()
    graph.invoke({"run_id": "t2", "request": {"question": "multiply 2 by 3"}, "principal": {}, "replans": 0},
                 config={"configurable": {"top_k": 8}})
    assert seen.get("top_k") == 8


def test_guard_catches_invented_numbers():
    facts = {"tool_results": [{"output": {"gross": 2999.0, "fee": 299.9, "shipping": 60.0, "refund": 2639.1,
                                          "fee_pct": 10, "delivered_on": "2026-10-03", "days": 3}}]}
    good = "Order O-100001 (SKU-E001), delivered 2026-10-03, 3 days ago: refund ₹2,639.10 = 2,999.00 - 10% fee (299.90) - 60.00."
    assert check_faithfulness(good, facts)["ok"]
    bad = check_faithfulness("You will get ₹2,700 back by 2026-10-09.", facts)
    assert bad["unsupported"] == ["2026-10-09", "2,700"]
    assert check_faithfulness("Night load is 38% of day load (about 0.4 kg CO2e/kWh).",
                              {"share": 0.38, "ef": 0.4})["ok"]
    assert check_faithfulness("Savings of ₹1,23,456 or 14.4k kWh; payback 3–6 months.",
                              {"inr": 123456, "kwh": 14400, "pb": [3, 6]})["ok"]
