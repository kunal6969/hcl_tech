# file: ui/streamlit_app.py
"""Executive UI. Thin client of the API contract: renders, never computes."""
from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent))

import api_client as api  # noqa: E402
from charts import bridge_waterfall, ranges_bar, show_chart  # noqa: E402
from components import answer_card, citation_chips, health_pills, kpi_row, step_timeline  # noqa: E402
from theme import inject_theme  # noqa: E402

st.set_page_config(page_title="AI Analyst Console", page_icon="◆", layout="wide", initial_sidebar_state="expanded")
inject_theme()

DEMO_QUESTIONS = [  # ← the statement's must-show demo items, in demo order
    "What is the return window for electronics?",
    "Can I return the headphones from order O-100001?",
    "Do you deliver to Antarctica?",
]

health, health_err = api.get("/health")
with st.sidebar:
    st.markdown("### System")
    health_pills(health, health_err)
    customer = st.text_input("Signed-in identity (header)", value="", placeholder="e.g. C1001").strip() or None
    as_of = st.date_input("As-of date", value=date.today())
    demo = st.selectbox("Demo questions", ["—"] + DEMO_QUESTIONS)

st.markdown('<div class="hero"><h1>AI Analyst Console</h1>'
            '<p>Grounded answers · deterministic tools · full audit trail</p></div>', unsafe_allow_html=True)
tab_ask, tab_ingest, tab_sources, tab_trace, tab_eval = st.tabs(["Ask", "Ingest", "Sources", "Traces", "Evaluation"])

with tab_ask:
    question = st.text_area("Question", value="" if demo == "—" else demo, height=80,
                            placeholder="Ask about a policy, an order, a bill…")
    go = st.button("Ask", type="primary", disabled=not question.strip())
    if go:
        body = {"question": question.strip(), "as_of_date": as_of.isoformat()}
        steps, response = [], None
        left, right = st.columns([2, 3], gap="large")
        with left:
            with st.status("Running…", expanded=True) as status:
                try:
                    for event in api.ask_stream(body, customer):
                        if event["event"] == "node":
                            steps.extend(event["steps"])
                            st.write(f"✓ **{event['node']}** " + ", ".join(
                                f"{s.get('tool') or ''} {s.get('status', '')}".strip() for s in event["steps"]))
                        else:
                            response = event["response"]
                    status.update(label="Done", state="complete", expanded=False)
                except Exception:
                    response, err = api.ask(body, customer)
                    status.update(label="Done" if response else "Failed", state="complete" if response else "error")
                    if err:
                        st.error(err)
        st.session_state["last"] = response
    response = st.session_state.get("last")
    if response:
        left, right = st.columns([2, 3], gap="large")
        with right:
            answer_card(response)
            citation_chips(response.get("citations", []), api.BASE)
            kpi_row(response)
            if response.get("bridge"):
                show_chart(bridge_waterfall(response["bridge"]), key="bridge")
                show_chart(ranges_bar(response["bridge"]), key="ranges")
        with left:
            record, _ = api.get(f"/audit/{response.get('trace_id') or response.get('run_id')}", customer)
            step_timeline((record or {}).get("steps", []))
            with st.expander("Raw response JSON"):
                st.json(response)

with tab_ingest:
    st.caption("Upload a document (PDF, DOCX, MD, HTML) or a data file (CSV, XLSX). Takes effect immediately.")
    up = st.file_uploader("File")
    meta_text = st.text_area("Metadata JSON", value=json.dumps(
        {"doc_id": "", "title": "", "authority_level": 2, "doc_type": "circular", "version": "1.0",
         "effective_from": date.today().isoformat(), "supersedes": "", "scope_categories": "ALL"}, indent=2), height=200)
    if st.button("Ingest", disabled=up is None):
        try:
            meta = json.loads(meta_text)
        except json.JSONDecodeError as err:
            st.error(f"Metadata is not valid JSON: {err}")
        else:
            res, err = api.ingest(up.name, up.getvalue(), {k: v for k, v in meta.items() if v != ""})
            if res:
                st.success("Ingested")
                st.json(res)
            else:
                st.error(err)

with tab_sources:
    rows, err = api.get("/sources")
    if rows:
        st.dataframe(rows, hide_index=True)
    else:
        st.info(err or "No sources ingested yet.")

with tab_trace:
    tid = st.text_input("Trace ID")
    if tid:
        rec, err = api.get(f"/audit/{tid.strip()}", customer)
        if rec:
            step_timeline(rec.get("steps", []))
            st.json(rec)
        else:
            st.warning(err)

with tab_eval:
    report = Path("eval/reports/latest.md")
    if report.exists():
        st.markdown(report.read_text())
    else:
        st.info("Run `python eval/run_eval.py` to populate.")
