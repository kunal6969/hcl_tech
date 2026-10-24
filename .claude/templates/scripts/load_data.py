# file: scripts/load_data.py
"""Load every table file in a directory: python scripts/load_data.py --dir test_data/ [--mode upsert|replace]"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import app.data.tables  # noqa: E402,F401  (registers TableSpecs)
from app.data.ingest import ingest_table  # noqa: E402
from app.data.validate import infer_table  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("--dir", required=True)
ap.add_argument("--mode", default="upsert", choices=["upsert", "replace", "append"])
args = ap.parse_args()
total_bad = 0
for path in sorted(Path(args.dir).glob("*")):
    if path.suffix.lower() not in (".csv", ".tsv", ".xlsx", ".xls", ".parquet", ".json") or not infer_table(path.name):
        continue
    res = ingest_table(path, mode=args.mode)
    total_bad += res["rows_rejected"]
    print(json.dumps({k: res.get(k) for k in ("table", "rows_loaded", "rows_rejected", "status", "data_version")}))
    for row in res.get("rejected_sample", []):
        print("   rejected:", row)
sys.exit(0)
