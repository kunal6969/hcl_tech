# file: tests/test_graph_supervisor.py
# Not applicable: this project uses a Tier-1 fixed graph, not a supervisor pattern.
import pytest
pytest.skip("Template test — not applicable to Tier-1 fixed graph", allow_module_level=True)
from pydantic import BaseModel

from app.graph import policy
from app.graph import supervisor as sup
from app.graph.nodes import route
from app.llm import gateway
from app.tools.registry import REGISTRY, ToolSpec, register


class Q(BaseModel):
    query: str


class N(BaseModel):
    x: float


@pytest.fixture(autouse=True)
def setup(monkeypatch, tmp_path):
    monkeypatch.setenv("MOCK_LLM", "true")
    monkeypatch.setenv("LLM_CACHE_PATH", str(tmp_path / "c.sqlite"))
    gateway.reset_gateway()
    saved = dict(REGISTRY)                      # restore, don't pop: real tools may already be registered
    register(ToolSpec("search_documents", "search", Q, lambda a, c: {
        "hits": 1, "evidence": [{"doc_id": "POL-1", "section": "3.1", "text": "Window is 7 days."}]}))
    register(ToolSpec("double", "double x", N, lambda a, c: {"result": a.x * 2}))
    monkeypatch.setitem(sup.WORKERS, "analytics_agent", {"tools": {"double"}, "purpose": "math"})
    monkeypatch.setattr(policy, "ENTITY_PATTERNS", {"number": r"\b\d+\b"})
    monkeypatch.setattr(policy, "INTENT_RULES", [{
        "intent": "combo", "pattern": r"double", "requires": ["number"],
        "plan": [{"tool": "search_documents", "args": {"query": "{question}"}},
                 {"tool": "double", "args": {"x": "{number}"}}]}])
    yield
    REGISTRY.clear()
    REGISTRY.update(saved)


def _state(q):
    return {"run_id": "s1", "request": {"question": q, "as_of_date": "2026-10-06"},
            "principal": {"subject_id": "C1001"}, "replans": 0}


def test_supervisor_runs_each_worker_once_and_synthesizes():
    out = sup.build_supervisor_graph(route).invoke(_state("double 21 per policy"))
    workers = [s["node"] for s in out["steps"] if s.get("tool") in {"search_documents", "double"}]
    assert sorted(workers) == ["analytics_agent", "retrieval_agent"]
    assert out["answer_type"] == "calculated" and "42" in out["answer"]
    assert out["evidence"][0]["doc_id"] == "POL-1"


def test_parallel_fan_out_merges_both_branches():
    out = sup.build_parallel_graph(route).invoke(_state("double 5 per policy"))
    assert {"retrieval_agent", "analytics_agent"} <= set(out["done_workers"])
    assert "10" in out["answer"]
