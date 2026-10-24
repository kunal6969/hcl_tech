# Charts and live components

One chart per question a manager would ask. Every series comes from contract fields or tool outputs.

| Manager question | Chart | Input |
|---|---|---|
| "Why did it go up 15%?" | bridge waterfall (base → causes → total) + ranges bar | response `bridge` |
| "Which assets use the most?" | Pareto (bars + cumulative %) | asset breakdown tool output |
| "When is energy wasted?" | hour × weekday heatmap, idle hours shaded | interval data via a tool/endpoint |
| "What changed after the new data?" | before/after diverging bars | `diff_bridges` output |
| "How good is the system?" | metric table from `eval/reports/latest.md` | eval runner |

## charts.py

**`ui/charts.py`** — Plotly: bridge waterfall, ranges bar, Pareto, heatmap, before/after (72 lines). Installed by `python .claude/bootstrap.py`; source: `.claude/templates/ui/charts.py`. Read it only when you need to edit it.

## Live execution stepper

Primary path: `api.ask_stream()` reads `/ask/stream` (skill 06) and writes one line per finished node into
`st.status(...)`; Streamlit renders each `st.write` as it happens, so judges watch input_guard → route →
execute → synthesize → guard → finalize live. Fallback path (stream unavailable): call `/ask`, then replay
the trace's `steps` with `step_timeline()`. Both paths end with the same answer card.

Keep the step labels in the domain's words: `execute · calculate_refund 4 ms`, `faithfulness_guard pass`.
Never show prompts or model reasoning — the audit summary is the product.

## Re-run diff view (late data drop)

After ingesting a corrected file: call the analysis endpoint again, fetch both run IDs' traces, call a
`diff` tool (or endpoint) that wraps `diff_bridges`, then render `before_after(rows)` plus a two-column
`st.metric` pair for the total with `delta=`. Narration comes from the diff rows, not from the LLM.

## Eval dashboard

Render `eval/reports/latest.md` directly (it is already a table). For a visual, parse the JSON report
and show a bar per metric with a 0–100% axis; colour bars below target (e.g. < 80%) in `UP` red.

## Pitfalls

- `use_container_width` is deprecated in newer Streamlit; `show_chart()` picks the right argument.
- Give every chart a `key` when it can render twice in one run (Streamlit duplicate-ID error otherwise).
- Expressions on their own line are "magic"-written by Streamlit; use `if/else` statements, not
  `a() if c else b()` expressions, for side-effect calls.
- Plotly text with `<br>` and inline `<span>` works in waterfall labels; keep it short for 1366-px screens.
