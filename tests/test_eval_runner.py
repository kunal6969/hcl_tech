# file: tests/test_eval_runner.py
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "eval"))

from run_eval import evaluate, get_path, percentile  # noqa: E402

RESP = {"trace_id": "t1", "answer_type": "calculated", "answer": "Refund is 2639.10 after a 10% fee.",
        "citations": [{"doc_id": "POL", "section": "5.1"}],
        "tools_invoked": [{"tool": "calculate_refund", "output": {"refund_amount": 2639.1, "fee_pct": 10}}],
        "bridge": [{"cause": "tariff", "pct_points": 8.1}]}
RECORD = {"sources_retrieved": [{"doc_id": "POL"}], "tools_invoked": RESP["tools_invoked"], "llm_calls": 2, "tokens": 900}


def test_get_path_filters_and_indexes():
    assert get_path(RESP, "tools_invoked[tool=calculate_refund].output.refund_amount") == 2639.1
    assert get_path(RESP, "bridge[cause=tariff].pct_points") == 8.1
    assert get_path(RESP, "citations[0].section") == "5.1"
    assert get_path(RESP, "citations[5].section") is None


def test_percentile_interpolates():
    assert percentile([100, 200, 300, 400], 50) == 250 and percentile([5], 95) == 5


def test_evaluate_scores_metrics_and_survives_crashes():
    cases = [
        {"id": "T1", "category": "fee", "request": {"question": "refund?"},
         "expect": {"answer_type": "calculated", "numbers": {"tools_invoked[tool=calculate_refund].output.refund_amount": 2639.10},
                    "tolerance": 0.01, "citations": ["POL#5.1"], "retrieval": ["POL"], "tools": ["calculate_refund"]}},
        {"id": "T2", "category": "unanswerable", "request": {"question": "antarctica?"},
         "expect": {"answer_type": "not_found"}},
        {"id": "T3", "category": "crash", "request": {"question": "boom"}, "expect": {"answer_type": "calculated"}},
    ]

    def call(case):
        if case["id"] == "T3":
            raise RuntimeError("server down")
        return RESP, RECORD, 120.0

    out = evaluate(cases, call)
    rows = {r["id"]: r for r in out["rows"]}
    assert rows["T1"]["passed"] and rows["T1"]["checks"]["faithful"]
    assert rows["T2"]["checks"]["abstention"] is False and not rows["T3"]["passed"]
    assert out["summary"]["tool_result"]["rate"] == 1.0 and out["summary"]["by_category"]["fee"] == "1/1"
