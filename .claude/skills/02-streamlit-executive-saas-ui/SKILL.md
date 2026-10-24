---
name: 02-streamlit-executive-saas-ui
description: Builds the Streamlit front end as a thin, premium client of the FastAPI contract - a glass "bento" design system with hidden Streamlit chrome and accessible contrast, answer cards with answer-type badges and citation chips, a live execution stepper fed by the SSE stream (falls back to post-hoc trace replay), Plotly bill-bridge waterfalls with ranges, Pareto and load heatmaps, before/after diff views for re-runs, an ingest console, sources and trace explorers, and an eval dashboard. Use this whenever the task mentions the UI, Streamlit, a dashboard, charts, the bill-bridge chart, visualising agent steps, the demo screen, or making the app look polished - and keep it time-boxed because the UI is scored only for usability.
---

# Streamlit executive UI (thin client, premium look, zero logic)

The UI is "scored only for usability", so it must be (1) correct — it only renders what the API returns,
(2) fast to build — everything below is copy-paste, ≤ 45 minutes in S6, and (3) clear for a manager in a
10-minute demo. It never computes numbers, never calls the LLM, never reads the databases directly.

- Design tokens, CSS, components: `references/custom-css-bento-design-system.md`
- Charts, live stepper, diff view, eval dashboard: `references/plotly-and-live-agent-components.md`

## 1. Layout blueprint

```
┌ sidebar ─────────────┐┌ main ───────────────────────────────────────────────────────────────┐
│ ● API ok  ● LLM ok   ││ Title (problem name)                         as-of date · data v12   │
│ ● Vector ok  v12     ││ ┌ Ask ─┬ Ingest ─┬ Sources ─┬ Traces ─┬ Evaluation ┐                  │
│ Identity: C1001 ▾    ││ │ question box ……………………………………… [Ask]                            │
│ As-of: 2026-10-06    ││ │ ┌ live steps ────────────┐ ┌ answer card (badge, text, chips) ┐ │
│ Provider: gemini→groq││ │ │ ✓ input_guard 3 ms     │ │ CALCULATED                        │ │
│ Demo questions ▾     ││ │ │ ✓ route (rule)         │ │ Yes — refund 2,639.10 …          │ │
│                      ││ │ │ ✓ execute: refund 4 ms │ └──────────────────────────────────┘ │
│                      ││ │ │ ✓ guard: pass          │ ┌ KPI tiles ┐┌ chart (waterfall) ┐  │
└──────────────────────┘└─┴──────────────────────────────────────────────────────────────────────┘
```

Rules that keep it honest in front of judges:
- The badge text is the raw `answer_type` from the API; colours encode it, text carries it (accessible).
- Citations are chips showing `doc_id · section · version · effective date`; clicking opens
  `/documents/{doc_id}` so a judge can check the cited page.
- Numbers shown in tiles/charts come from `tools_invoked[*].output` or contract fields (`bridge`,
  `recommendations`) — never parsed out of prose.
- Untrusted text (answers, document snippets, notes) is HTML-escaped before it goes into custom HTML.
- A "demo questions" picker in the sidebar holds the statement's must-show items, so the demo is clicks.

## 2. API client

**`ui/api_client.py`** — thin HTTP client: get/ask/ask_stream/ingest, returns (data, error) (39 lines). Installed by `python .claude/bootstrap.py`; source: `.claude/templates/ui/api_client.py`. Read it only when you need to edit it.

## 3. The app

**`ui/streamlit_app.py`** — the app: sidebar, Ask/Ingest/Sources/Traces/Evaluation tabs, live stepper (109 lines). Installed by `python .claude/bootstrap.py`; source: `.claude/templates/ui/streamlit_app.py`. Read it only when you need to edit it.

**`.streamlit/config.toml`** — Streamlit theme matching the design tokens (12 lines). Installed by `python .claude/bootstrap.py`; source: `.claude/templates/.streamlit/config.toml`. Read it only when you need to edit it.

## 4. Build order (S6, time-boxed)

1. Copy `ui/` files + `.streamlit/config.toml`; run `streamlit run ui/streamlit_app.py` against the API.
2. Fill `DEMO_QUESTIONS` from the demo script; rename `ASK_PATH`; adapt `kpi_row` to the contract fields.
3. Add the problem's chart (bridge waterfall, Pareto of assets, load heatmap) from the charts reference.
4. Check: works with the API down (shows a clear message), with MOCK_LLM, at 1366×768, and in light mode.
5. Stop. Remaining time goes to eval and README, which score more.

## 5. Test (headless, no browser)

**`tests/test_ui_smoke.py`** — from pathlib import Path (20 lines). Installed by `python .claude/bootstrap.py`; source: `.claude/templates/tests/test_ui_smoke.py`. Read it only when you need to edit it.
