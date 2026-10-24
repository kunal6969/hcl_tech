#!/usr/bin/env python3
"""Install the tested project templates from .claude/templates/ into this repository.

Writes real files instead of having Claude retype them, which is the single biggest token
saving in the build. Existing files are never overwritten unless --force is given.

Usage
  python .claude/bootstrap.py --list                    what exists, and where it lands
  python .claude/bootstrap.py --tier core               S1 skeleton: llm, graph, tools, api, trace, tests, docker
  python .claude/bootstrap.py --tier core,data          + schemas, validation, loader, ingest, registry, rag
  python .claude/bootstrap.py --tier analytics          archetype B: cleaning, baseline, bridge, anomaly, savings
  python .claude/bootstrap.py --tier ui,eval            S5/S6: Streamlit client, eval harness, scripts
  python .claude/bootstrap.py --all                     everything (still skips files you already have)
  python .claude/bootstrap.py --all --dry-run           show what would be written
Flags: --force overwrite existing files · --dest <dir> install elsewhere · --quiet
"""
from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

TEMPLATES = Path(__file__).resolve().parent / "templates"
PROJECT = Path(__file__).resolve().parents[1]

# tier -> path prefixes. A file belongs to the first tier that matches.
TIERS: dict[str, tuple[str, ...]] = {
    "core": ("app/llm/", "app/graph/state.py", "app/graph/policy.py", "app/graph/nodes.py", "app/graph/build.py",
             "app/tools/registry.py", "app/tools/common.py", "app/tools/catalog.py", "app/api/", "app/trace/",
             "tests/test_gateway.py", "tests/test_graph_unified.py", "tests/test_api_contract.py",
             "Dockerfile", "docker-compose.yml", "requirements.txt"),
    "data": ("app/data/", "app/rag/", "scripts/load_data.py", "tests/test_data_layer.py",
             "tests/test_precedence.py", "tests/test_search_tool.py"),
    "tools": ("app/tools/search.py", "app/tools/example_orders.py", "tests/test_tools_examples.py"),
    "analytics": ("app/analytics/", "tests/test_analytics.py"),
    "agents": ("app/graph/supervisor.py", "tests/test_graph_supervisor.py"),
    "ui": ("ui/", ".streamlit/", "tests/test_ui_smoke.py"),
    "eval": ("eval/", "scripts/export_traces.py", "tests/test_eval_runner.py"),
}
# files to rename on install (template name -> destination name)
RENAME = {"eval/cases.example.yaml": "eval/cases.yaml", "eval/configs.example.yaml": "eval/configs.yaml"}
# files that are problem-specific stubs: Claude must edit them in the stage that owns them
EDIT_FIRST = {"app/graph/policy.py": "S4 — answer types, messages, entity regexes, intent rules",
              "app/api/schemas.py": "S1 — transcribe the statement's contract verbatim",
              "app/data/tables.py": "S2 — transcribe the statement's schema annex",
              "app/tools/catalog.py": "S3 — import your tool modules",
              "eval/cases.yaml": "S5 — write the problem's cases"}
PACKAGE_DIRS = ("app", "app/api", "app/graph", "app/tools", "app/llm", "app/data", "app/rag", "app/analytics",
                "app/trace")


def tier_of(rel: str) -> str:
    for tier, prefixes in TIERS.items():
        if any(rel == p or rel.startswith(p) for p in prefixes):
            return tier
    return "other"


def templates() -> list[str]:
    return sorted(str(p.relative_to(TEMPLATES)) for p in TEMPLATES.rglob("*") if p.is_file())


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--tier", default="", help="comma-separated: " + ",".join(TIERS))
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--quiet", action="store_true")
    ap.add_argument("--dest", default=str(PROJECT))
    args = ap.parse_args(argv)
    if not TEMPLATES.is_dir():
        print(f"no templates at {TEMPLATES}", file=sys.stderr)
        return 2
    files = templates()
    if args.list:
        for tier in list(TIERS) + ["other"]:
            group = [f for f in files if tier_of(f) == tier]
            if group:
                print(f"\n[{tier}]")
                for f in group:
                    print(f"  {RENAME.get(f, f)}")
        return 0
    wanted = set(TIERS) if args.all else {t.strip() for t in args.tier.split(",") if t.strip()}
    unknown = wanted - set(TIERS)
    if unknown:
        print(f"unknown tier(s): {sorted(unknown)}; choose from {','.join(TIERS)}", file=sys.stderr)
        return 2
    if not wanted:
        ap.print_help()
        return 2
    dest_root = Path(args.dest).resolve()
    written, skipped, edit_now = [], [], []
    for rel in files:
        if tier_of(rel) not in wanted:
            continue
        out_rel = RENAME.get(rel, rel)
        dest = dest_root / out_rel
        if dest.exists() and not args.force:
            skipped.append(out_rel)
            continue
        if not args.dry_run:
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(TEMPLATES / rel, dest)
        written.append(out_rel)
        if out_rel in EDIT_FIRST:
            edit_now.append(out_rel)
    if not args.dry_run:
        for pkg in PACKAGE_DIRS:
            d = dest_root / pkg
            if d.is_dir() and not (d / "__init__.py").exists():
                (d / "__init__.py").write_text("")
        pyproject = dest_root / "pyproject.toml"
        if not pyproject.exists():
            pyproject.write_text('[tool.ruff]\nline-length = 120\n\n[tool.ruff.lint]\n'
                                 'select = ["E", "F", "W", "I", "B"]\n\n'
                                 '[tool.pytest.ini_options]\npythonpath = ["."]\n')
            written.append("pyproject.toml")
        gitignore = dest_root / ".gitignore"
        if not gitignore.exists():
            gitignore.write_text("data/\n.env\n__pycache__/\n*.pyc\n.pytest_cache/\n.ruff_cache/\n"
                                 "eval/reports/*.json\n.venv/\n")
            written.append(".gitignore")
    if not args.quiet:
        verb = "would write" if args.dry_run else "wrote"
        print(f"{verb} {len(written)} file(s); skipped {len(skipped)} existing"
              + (" (use --force to overwrite)" if skipped else ""))
        for f in written:
            print("  +", f)
        for f in skipped[:10]:
            print("  =", f)
        if edit_now:
            print("\nEdit these for this problem before the next test run:")
            for f in edit_now:
                print(f"  {f:28s} {EDIT_FIRST[f]}")
        if not args.dry_run and written:
            print("\nNext: pip install -r requirements.txt  &&  MOCK_LLM=true pytest -q")
    return 0


if __name__ == "__main__":
    sys.exit(main())
