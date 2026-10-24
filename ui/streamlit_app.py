"""
streamlit_app.py — Hospital Patient Services Assistant UI.

Two tabs:
  1. Patient Chat  — ask questions, see answer-type badges, citations, tool trace
  2. Admin Ingest  — upload policy documents (X-Role: admin only)

The UI is a thin client; it never computes — it calls the FastAPI backend.
Run with: streamlit run ui/streamlit_app.py
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import requests
import streamlit as st

# ── page config must be first Streamlit call ─────────────────────────────────
st.set_page_config(
    page_title="Hospital Patient Services",
    page_icon="🏥",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── config ────────────────────────────────────────────────────────────────────
API_BASE = os.environ.get("API_BASE_URL", "http://localhost:8005")

# Answer-type badge colours (background, text)
BADGE_COLOURS = {
    "retrieved_fact":       ("#1a7f5e", "#ffffff"),
    "calculated":           ("#1a5f9e", "#ffffff"),
    "action_completed":     ("#4a7f1a", "#ffffff"),
    "clarification_needed": ("#8f6a00", "#ffffff"),
    "not_found":            ("#555555", "#ffffff"),
    "refused":              ("#9e1a1a", "#ffffff"),
    "conflict_flagged":     ("#7f3a9e", "#ffffff"),
}

DEMO_QUESTIONS = [
    "What are the visiting hours for ICU patients?",
    "What are my upcoming appointments?",
    "Is my Knee Replacement surgery covered by my insurance?",
    "What were my recent lab results?",
    "Are there any interactions between Warfarin and Aspirin?",
    "How do I schedule an MRI scan?",
    "What happens on the day I am discharged?",
    "I want to reschedule appointment A001 to 2026-11-20 at 10:00",
]

PATIENTS = {
    "P1001": "P1001 — Aarav Sharma (Gold plan)",
    "P1002": "P1002 — Priya Nair (Silver plan)",
    "P1004": "P1004 — Meera Patel (Expired plan — E1)",
    "P1010": "P1010 — Kavya Reddy (Pending lab — E3)",
    "P1012": "P1012 — Rohan Verma (No insurance — E4)",
}


# ── helpers ───────────────────────────────────────────────────────────────────

def _badge(answer_type: str) -> str:
    """Render a coloured badge for the answer_type."""
    bg, fg = BADGE_COLOURS.get(answer_type, ("#333333", "#ffffff"))
    return (
        f'<span style="background:{bg};color:{fg};padding:3px 10px;'
        f'border-radius:12px;font-size:0.78em;font-weight:600;">'
        f'{answer_type}</span>'
    )


def _call_chat(question: str, patient_id: str, role: str = "patient") -> dict:
    """POST /chat with identity headers; return the full response dict."""
    try:
        r = requests.post(
            f"{API_BASE}/chat",
            json={"question": question},
            headers={"X-Patient-Id": patient_id, "X-Role": role},
            timeout=60,
        )
        return r.json()
    except Exception as e:
        return {"error": str(e), "answer": f"API error: {e}", "answer_type": "not_found",
                "citations": [], "tools_invoked": [], "trace_id": "", "explanation": ""}


def _get_health() -> dict:
    try:
        return requests.get(f"{API_BASE}/health", timeout=5).json()
    except Exception:
        return {"status": "unreachable", "sqlite": False, "chromadb": False, "llm_mock": False}


def _ingest_doc(file_bytes: bytes, filename: str, doc_name: str, authority: str,
                version: str, effective_date: str, section: str) -> dict:
    """POST /admin/ingest with admin role."""
    try:
        r = requests.post(
            f"{API_BASE}/admin/ingest",
            files={"file": (filename, file_bytes, "application/octet-stream")},
            data={
                "doc_name": doc_name,
                "authority": authority,
                "version": version,
                "effective_date": effective_date,
                "section": section,
            },
            headers={"X-Patient-Id": "P0001", "X-Role": "admin"},
            timeout=60,
        )
        return r.json()
    except Exception as e:
        return {"status": "error", "message": str(e)}


# ── sidebar ───────────────────────────────────────────────────────────────────

with st.sidebar:
    st.markdown("## 🏥 Patient Services")
    st.markdown("---")

    # Patient picker
    st.markdown("### Identity")
    patient_id = st.selectbox(
        "Patient ID",
        options=list(PATIENTS.keys()),
        format_func=lambda k: PATIENTS[k],
        key="patient_id",
    )

    st.markdown("---")

    # Health status
    st.markdown("### System Status")
    health = _get_health()
    if health.get("status") == "unreachable":
        st.error("API unreachable — start the server with: uvicorn app.api.main:app --port 8000")
    status_colour = "🟢" if health.get("status") == "ok" else "🔴"
    st.markdown(f"{status_colour} API: **{health.get('status', 'unknown')}**")
    st.markdown(f"{'🟢' if health.get('sqlite') else '🔴'} SQLite")
    st.markdown(f"{'🟢' if health.get('chromadb') else '🔴'} ChromaDB")
    st.markdown(f"{'🟡' if health.get('llm_mock') else '🟢'} LLM {'(mock)' if health.get('llm_mock') else '(live)'}")

    st.markdown("---")
    st.markdown("### Demo Questions")
    for q in DEMO_QUESTIONS:
        if st.button(q[:55] + ("…" if len(q) > 55 else ""), key=f"demo_{q[:20]}", use_container_width=True):
            st.session_state["prefill_question"] = q


# ── main area ─────────────────────────────────────────────────────────────────

if health.get("status") == "unreachable":
    st.error("API unreachable — start the server with: uvicorn app.api.main:app --port 8000")

tab_chat, tab_admin = st.tabs(["💬 Patient Chat", "📁 Admin Ingest"])

# ════════════════════════════════════════════════════════════════════════════
# TAB 1: Patient Chat
# ════════════════════════════════════════════════════════════════════════════
with tab_chat:
    st.markdown("## Patient Services Chat")
    st.caption(f"Logged in as **{patient_id}** · Identity from headers only · All responses are grounded and traced.")

    # Chat history stored in session state
    if "messages" not in st.session_state:
        st.session_state["messages"] = []

    # Render existing chat history
    for msg in st.session_state["messages"]:
        with st.chat_message(msg["role"]):
            if msg["role"] == "assistant":
                col1, col2 = st.columns([6, 1])
                with col1:
                    st.markdown(msg["content"])
                with col2:
                    st.markdown(_badge(msg.get("answer_type", "not_found")), unsafe_allow_html=True)
                # Citations
                cits = msg.get("citations", [])
                if cits:
                    with st.expander(f"📎 {len(cits)} citation(s)", expanded=False):
                        for c in cits:
                            doc = c.get("doc") or c.get("system", "Hospital System")
                            ver = f" v{c['version']}" if c.get("version") else ""
                            sec = f" § {c['section']}" if c.get("section") else ""
                            st.markdown(f"- **{doc}**{ver}{sec}")
                # Tools invoked
                tools = msg.get("tools_invoked", [])
                if tools:
                    with st.expander(f"🔧 {len(tools)} tool(s) invoked", expanded=False):
                        for t in tools:
                            st.markdown(f"- `{t.get('tool')}` — {t.get('result_summary', '')}")
                # Trace ID
                if msg.get("trace_id"):
                    st.caption(f"Trace: `{msg['trace_id']}`")
            else:
                st.markdown(msg["content"])

    # Question input (pre-fill from demo button if set)
    prefill = st.session_state.pop("prefill_question", "")
    question = st.chat_input("Ask a question about hospital policies, your appointments, labs or medications…")
    if not question and prefill:
        question = prefill

    if question:
        # Add user message to history
        st.session_state["messages"].append({"role": "user", "content": question})
        with st.chat_message("user"):
            st.markdown(question)

        # Call API
        with st.chat_message("assistant"):
            with st.spinner("Thinking…"):
                resp = _call_chat(question, patient_id)

            answer = resp.get("answer", "")
            answer_type = resp.get("answer_type", "not_found")
            citations = resp.get("citations", [])
            tools = resp.get("tools_invoked", [])
            trace_id = resp.get("trace_id", "")

            col1, col2 = st.columns([6, 1])
            with col1:
                st.markdown(answer)
            with col2:
                st.markdown(_badge(answer_type), unsafe_allow_html=True)

            if citations:
                with st.expander(f"📎 {len(citations)} citation(s)", expanded=True):
                    for c in citations:
                        doc = c.get("doc") or c.get("system", "Hospital System")
                        ver = f" v{c['version']}" if c.get("version") else ""
                        sec = f" § {c['section']}" if c.get("section") else ""
                        st.markdown(f"- **{doc}**{ver}{sec}")

            if tools:
                with st.expander(f"🔧 {len(tools)} tool(s) invoked", expanded=False):
                    for t in tools:
                        st.markdown(f"- `{t.get('tool')}` — {t.get('result_summary', '')}")

            if trace_id:
                st.caption(f"Trace: `{trace_id}`")

        # Save to history
        st.session_state["messages"].append({
            "role": "assistant",
            "content": answer,
            "answer_type": answer_type,
            "citations": citations,
            "tools_invoked": tools,
            "trace_id": trace_id,
        })

    # Clear chat button
    if st.session_state.get("messages"):
        if st.button("🗑 Clear conversation", use_container_width=False):
            st.session_state["messages"] = []
            st.rerun()

# ════════════════════════════════════════════════════════════════════════════
# TAB 2: Admin Ingest
# ════════════════════════════════════════════════════════════════════════════
with tab_admin:
    st.markdown("## Admin Document Ingest")
    st.caption("Upload new policy documents to the knowledge base. Requires admin role.")
    st.warning("This endpoint requires **X-Role: admin**. Patient accounts cannot ingest documents.")

    with st.form("ingest_form"):
        uploaded = st.file_uploader("Policy document (PDF, MD, or TXT)", type=["pdf", "md", "txt"])
        col1, col2 = st.columns(2)
        with col1:
            doc_name = st.text_input("Document name", placeholder="ICU Visiting Hours Policy")
            authority = st.selectbox(
                "Authority level",
                ["hospital_policy", "clinical_guideline", "government_regulation"],
            )
            version = st.text_input("Version", placeholder="2.0")
        with col2:
            section = st.text_input("Section", placeholder="Visitor Management")
            effective_date = st.date_input("Effective date")

        submitted = st.form_submit_button("Ingest Document", use_container_width=True)

    if submitted and uploaded:
        with st.spinner("Ingesting document…"):
            result = _ingest_doc(
                file_bytes=uploaded.read(),
                filename=uploaded.name,
                doc_name=doc_name or uploaded.name,
                authority=authority,
                version=version or "1.0",
                effective_date=str(effective_date),
                section=section or "General",
            )
        if result.get("status") == "ok":
            st.success(
                f"Document ingested: **{result.get('doc_id', '')}** — "
                f"{result.get('chunks_added', 0)} chunks added."
            )
            st.caption(result.get("message", ""))
        else:
            st.error(f"Ingest failed: {result.get('message', result)}")
    elif submitted and not uploaded:
        st.error("Please select a file to upload.")
