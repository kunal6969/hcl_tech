# file: eval/run_eval.py
"""Evaluation runner.
  python eval/run_eval.py --mode http --base-url http://localhost:8000
  python eval/run_eval.py --mode inproc --compare A B --configs eval/configs.yaml
Writes eval/reports/<run>.json and .md. Method: exact match for types/numbers (with tolerance),
substring rules for text, set inclusion for citations/tools, guard-based number faithfulness."""
from __future__ import annotations

import argparse
import json
import os
import re
import statistics
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

ABSTAIN_TYPES = {"not_found", "not_in_data"}
Caller = Callable[[dict], tuple[dict, dict, float]]   # case -> (response, audit record, latency_ms)


def get_path(obj: Any, path: str) -> Any:
    """'a.b', 'a[0].b', 'bridge[cause=tariff].pct_points', 'tools_invoked[tool=x].output.y'."""
    for part in re.findall(r"[^.\[\]]+|\[[^\]]*\]", path):
        if obj is None:
            return None
        if part.startswith("["):
            inner = part[1:-1]
            if "=" in inner:
                key, val = inner.split("=", 1)
                obj = next((x for x in obj if isinstance(x, dict) and str(x.get(key)) == val), None)
            else:
                idx = int(inner)
                obj = obj[idx] if isinstance(obj, list) and -len(obj) <= idx < len(obj) else None
        else:
            obj = obj.get(part) if isinstance(obj, dict) else None
    return obj


def percentile(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    s = sorted(values)
    k = (len(s) - 1) * p / 100
    lo, hi = int(k), min(int(k) + 1, len(s) - 1)
    return s[lo] + (s[hi] - s[lo]) * (k - lo)


def _text(resp: dict) -> str:
    return " ".join(str(resp.get(k, "")) for k in ("answer", "summary", "explanation"))


def check_case(case: dict, resp: dict, record: dict) -> dict:
    exp = case.get("expect", {})
    text = _text(resp).lower()
    res: dict[str, bool | None] = {}
    if "answer_type" in exp:
        res["answer_type"] = resp.get("answer_type") == exp["answer_type"]
    if "answer_type_in" in exp:
        res["answer_type"] = resp.get("answer_type") in exp["answer_type_in"]
    content = []
    if exp.get("answer_contains"):
        content.append(all(s.lower() in text for s in exp["answer_contains"]))
    if exp.get("answer_contains_any"):
        content.append(any(s.lower() in text for s in exp["answer_contains_any"]))
    if exp.get("answer_not_contains"):
        content.append(not any(s.lower() in text for s in exp["answer_not_contains"]))
    if exp.get("numbers"):
        tol = float(exp.get("tolerance", 1e-6))
        nums_ok = []
        for path, want in exp["numbers"].items():
            got = get_path(resp, path)
            nums_ok.append(isinstance(got, (int, float)) and not isinstance(got, bool) and abs(got - float(want)) <= tol)
        res["tool_result"] = all(nums_ok)
        content.append(res["tool_result"])
    if content:
        res["answer_correct"] = all(content)
    if exp.get("citations"):
        cited = {c.get("doc_id") for c in resp.get("citations", [])} | \
                {f"{c.get('doc_id')}#{c.get('section')}" for c in resp.get("citations", [])}
        res["citation"] = all(c in cited for c in exp["citations"])
    if exp.get("retrieval"):
        got = {s.get("doc_id") for s in record.get("sources_retrieved", [])}
        res["retrieval_hit"] = any(d in got for d in exp["retrieval"])
    if exp.get("tools"):
        used = {t.get("tool") for t in resp.get("tools_invoked", [])} | \
               {t.get("tool") for t in record.get("tools_invoked", [])}
        res["tools"] = all(t in used for t in exp["tools"])
    want_type = exp.get("answer_type") or (exp.get("answer_type_in") or [None])[0]
    if want_type is not None:
        res["abstention"] = (want_type in ABSTAIN_TYPES) == (resp.get("answer_type") in ABSTAIN_TYPES)
    if want_type == "refused":
        res["refusal"] = resp.get("answer_type") == "refused"
    res["faithful"] = faithfulness(case, resp, record)
    return res


def faithfulness(case: dict, resp: dict, record: dict) -> bool:
    from app.llm.guard import check_faithfulness
    facts = {"tools": [t.get("output") for t in record.get("tools_invoked", resp.get("tools_invoked", []))],
             "citations": resp.get("citations", []), "rules": resp.get("applied_rules", []),
             "bridge": resp.get("bridge"), "recommendations": resp.get("recommendations"),
             "as_of": resp.get("as_of_date"), "assumptions": resp.get("assumptions", [])}
    return check_faithfulness(_text(resp), facts, question=case["request"].get("question", ""))["ok"]


METRICS = ["answer_type", "answer_correct", "tool_result", "citation", "abstention", "retrieval_hit",
           "refusal", "tools", "faithful"]


def evaluate(cases: list[dict], call: Caller, sleep: float = 0.0) -> dict:
    rows = []
    for case in cases:
        try:
            resp, record, ms = call(case)
            checks = check_case(case, resp, record)
            error = None
        except Exception as err:  # a crash is a failed case, not a crashed eval
            resp, record, ms, checks, error = {}, {}, 0.0, {m: False for m in ("answer_type",)}, repr(err)
        rows.append({"id": case["id"], "category": case.get("category", ""), "tags": case.get("tags", []),
                     "checks": checks, "passed": all(v for v in checks.values() if v is not None),
                     "answer_type": resp.get("answer_type"), "latency_ms": ms,
                     "llm_calls": record.get("llm_calls", 0), "tokens": record.get("tokens", 0),
                     "trace_id": resp.get("trace_id") or resp.get("run_id"), "error": error,
                     "answer": _text(resp)[:300]})
        time.sleep(sleep)
    return {"rows": rows, "summary": summarise(rows)}


def summarise(rows: list[dict]) -> dict:
    out: dict[str, Any] = {"cases": len(rows), "passed": sum(r["passed"] for r in rows)}
    for m in METRICS:
        vals = [r["checks"][m] for r in rows if r["checks"].get(m) is not None]
        out[m] = {"rate": round(sum(vals) / len(vals), 3) if vals else None, "n": len(vals)}
    lat = [r["latency_ms"] for r in rows if r["latency_ms"]]
    out["latency_ms"] = {"p50": round(percentile(lat, 50), 1), "p95": round(percentile(lat, 95), 1)}
    out["llm_calls_mean"] = round(statistics.fmean([r["llm_calls"] for r in rows]), 2) if rows else 0
    out["tokens_mean"] = round(statistics.fmean([r["tokens"] for r in rows]), 1) if rows else 0
    cats: dict[str, list] = {}
    for r in rows:
        cats.setdefault(r["category"], []).append(r["passed"])
    out["by_category"] = {c: f"{sum(v)}/{len(v)}" for c, v in sorted(cats.items())}
    return out


def http_caller(base_url: str, endpoint: str = "/ask", audit_path: str = "/audit/{id}") -> Caller:
    import httpx
    admin = os.getenv("ADMIN_TOKEN")

    def call(case: dict):
        headers = dict(case.get("headers") or {})
        t0 = time.perf_counter()
        resp = httpx.post(base_url + endpoint, json=case["request"], headers=headers, timeout=180).json()
        ms = (time.perf_counter() - t0) * 1000
        tid = resp.get("trace_id") or resp.get("run_id")
        audit_headers = {**headers, **({"X-Admin-Token": admin} if admin else {})}
        r = httpx.get(base_url + audit_path.format(id=tid), headers=audit_headers, timeout=30)
        return resp, (r.json() if r.status_code == 200 else {}), ms
    return call


def inproc_caller(configurable: dict | None = None) -> Caller:
    import app.data.tables  # noqa: F401
    import app.tools.catalog  # noqa: F401
    from app.api.main import principal_from
    from app.api.schemas import AskRequest
    from app.api.service import answer

    def call(case: dict):
        t0 = time.perf_counter()
        resp, record = answer(AskRequest(**case["request"]),
                              principal_from((case.get("headers") or {}).get("X-Customer-Id")),
                              configurable, endpoint="eval")
        return resp, record, (time.perf_counter() - t0) * 1000
    return call


def _git_commit() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], text=True).strip()
    except Exception:
        return "n/a"


def to_markdown(results: dict[str, dict], method: str) -> str:
    names = list(results)
    lines = [f"# Evaluation report — {datetime.now(timezone.utc):%Y-%m-%d %H:%M} UTC, commit {_git_commit()}", "",
             f"Method: {method}", "", "| Metric | " + " | ".join(names) + " |", "|---|" + "---|" * len(names)]
    for m in METRICS:
        cells = []
        for n in names:
            s = results[n]["summary"][m]
            cells.append("n/a" if s["rate"] is None else f"{s['rate']:.0%} (n={s['n']})")
        lines.append(f"| {m} | " + " | ".join(cells) + " |")
    for key, label in (("p50", "latency p50 ms"), ("p95", "latency p95 ms")):
        lines.append(f"| {label} | " + " | ".join(str(results[n]["summary"]["latency_ms"][key]) for n in names) + " |")
    lines.append("| LLM calls / question | " + " | ".join(str(results[n]["summary"]["llm_calls_mean"]) for n in names) + " |")
    lines.append("| tokens / question | " + " | ".join(str(results[n]["summary"]["tokens_mean"]) for n in names) + " |")
    for n in names:
        lines += ["", f"## {n}: by category", "", "| Category | Passed |", "|---|---|"]
        lines += [f"| {c} | {v} |" for c, v in results[n]["summary"]["by_category"].items()]
        fails = [r for r in results[n]["rows"] if not r["passed"]]
        if fails:
            lines += ["", "Failures:", ""] + [f"- {r['id']} ({r['category']}): got `{r['answer_type']}` — "
                                              f"{[k for k, v in r['checks'].items() if v is False]} {r['error'] or ''}"
                                              for r in fails]
    return "\n".join(lines) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cases", default="eval/cases.yaml")
    ap.add_argument("--mode", choices=["http", "inproc"], default="http")
    ap.add_argument("--base-url", default="http://localhost:8000")
    ap.add_argument("--endpoint", default="/ask")
    ap.add_argument("--configs", default="eval/configs.yaml")
    ap.add_argument("--compare", nargs="*", default=[])
    ap.add_argument("--sleep", type=float, default=0.0)
    ap.add_argument("--method", default="exact match (types, numbers ± tolerance), substring rules, set inclusion "
                                        "for citations/tools, guard-based number faithfulness")
    args = ap.parse_args()
    cases = yaml.safe_load(Path(args.cases).read_text())
    results: dict[str, dict] = {}
    if args.mode == "http":
        results["live"] = evaluate(cases, http_caller(args.base_url, args.endpoint), args.sleep)
    else:
        configs = yaml.safe_load(Path(args.configs).read_text()) if Path(args.configs).exists() else {}
        for name in args.compare or ["default"]:
            cfg = configs.get(name, {})
            old = {k: os.environ.get(k) for k in cfg.get("env", {})}
            os.environ.update({k: str(v) for k, v in cfg.get("env", {}).items()})
            from app.llm.gateway import reset_gateway
            from app.rag.index import reset_index
            reset_gateway()
            reset_index()
            results[name] = evaluate(cases, inproc_caller(cfg.get("configurable")), args.sleep)
            for k, v in old.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v
    out = Path("eval/reports")
    out.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M")
    (out / f"{stamp}.json").write_text(json.dumps(results, indent=2, default=str))
    (out / f"{stamp}.md").write_text(to_markdown(results, args.method))
    (out / "latest.md").write_text(to_markdown(results, args.method))
    for name, res in results.items():
        print(name, json.dumps({k: v for k, v in res["summary"].items() if k != "by_category"}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
