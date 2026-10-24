# file: scripts/export_traces.py
"""Export one trace per answer type (default 3+) to deliverables/traces/ for the submission."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.trace.store import list_traces  # noqa: E402

out = Path("deliverables/traces")
out.mkdir(parents=True, exist_ok=True)
picked: dict[str, dict] = {}
for rec in list_traces(500):
    picked.setdefault(rec.get("answer_type") or "unknown", rec)
for answer_type, rec in picked.items():
    (out / f"{answer_type}_{rec['trace_id']}.json").write_text(json.dumps(rec, indent=2, default=str))
    print("wrote", answer_type, rec["trace_id"])
if len(picked) < 3:
    print("WARNING: fewer than 3 answer types in traces - run the demo questions first")
