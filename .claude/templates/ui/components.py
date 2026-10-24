# file: ui/components.py
"""Small HTML components. Everything from the API is untrusted: escape before rendering."""
from __future__ import annotations

from html import escape

import streamlit as st
from theme import ANSWER_COLORS


def _html(markup: str) -> None:
    st.markdown(markup, unsafe_allow_html=True)


def badge(answer_type: str) -> str:
    color = ANSWER_COLORS.get(answer_type, "#9AA8BC")
    return f'<span class="badge" style="color:{color}">{escape(answer_type.replace("_", " "))}</span>'


def answer_card(resp: dict) -> None:
    text = escape(resp.get("answer") or resp.get("summary") or "")
    expl = escape(resp.get("explanation") or "")
    assumptions = "".join(f"<li>{escape(a)}</li>" for a in resp.get("assumptions", []))
    _html(f'<div class="answer-card">{badge(resp.get("answer_type", ""))}'
          f'<div class="text">{text}</div>'
          + (f'<div class="expl">{expl}</div>' if expl else "")
          + (f'<div class="expl"><b>Assumptions</b><ul>{assumptions}</ul></div>' if assumptions else "")
          + "</div>")


def citation_chips(citations: list[dict], base_url: str) -> None:
    if not citations:
        return
    chips = []
    for c in citations:
        label = " · ".join(x for x in (c.get("doc_id"), c.get("section") and f"§{c['section']}",
                                         c.get("version") and f"v{c['version']}", c.get("effective_from")) if x)
        href = f"{base_url}/documents/{escape(c.get('doc_id', ''))}"
        chips.append(f'<a class="chip" href="{href}" target="_blank" rel="noopener">{escape(label)}</a>')
    _html(f'<div class="chips">{"".join(chips)}</div>')


def kpi_row(resp: dict) -> None:
    """Tiles from tool outputs only. Adapt the picks to the contract (refund, window, payback, bridge total…)."""
    tiles = []
    for t in resp.get("tools_invoked", [])[:4]:
        out = t.get("output") if isinstance(t.get("output"), dict) else {}
        for key, value in list(out.items())[:2]:
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                tiles.append((key.replace("_", " "), f"{value:,.2f}".rstrip("0").rstrip("."), t.get("tool", "")))
    for rec in resp.get("recommendations", [])[:2]:
        lo, hi = rec.get("saving_money_per_year", [0, 0])
        tiles.append((rec.get("action", "")[:28], f"{lo:,.0f}–{hi:,.0f}", "saving / year"))
    if tiles:
        _html('<div class="bento">' + "".join(
            f'<div class="tile"><div class="label">{escape(a)}</div><div class="value">{escape(b)}</div>'
            f'<div class="sub">{escape(c)}</div></div>' for a, b, c in tiles[:6]) + "</div>")


def health_pills(health: dict | None, error: str | None) -> None:
    if not health:
        st.error(error or "API unreachable")
        return
    def pill(name: str, ok: bool, note: str = "") -> str:
        color = "#3FB8AF" if ok else "#F2665E"
        return f'<span class="pill"><span class="dot" style="background:{color}"></span>{escape(name)} {escape(note)}</span>'
    llm = health.get("llm", {})
    _html(pill("API", True) + pill("SQLite", health.get("sqlite") == "ok")
          + pill("Vectors", str(health.get("vector_store", "")).startswith("ok"))
          + pill("LLM", llm.get("status") == "ok", "→".join(llm.get("chain", [])))
          + pill("data", True, f"v{health.get('data_version', '?')}"))


def step_timeline(steps: list[dict]) -> None:
    if not steps:
        return
    icon = {"ok": "✓", "rule": "✓", "llm": "✓", "pass": "✓", "fallback": "↺", "fixed": "↺", "refused": "⛔",
            "error": "✕", "clarify": "?"}
    rows = []
    for s in steps:
        label = s.get("node", "") + (f" · {s['tool']}" if s.get("tool") else "")
        ms = f"{s['ms']:.0f} ms" if isinstance(s.get("ms"), (int, float)) else ""
        rows.append(f'<div class="step"><span>{icon.get(s.get("status", ""), "•")}</span>'
                    f'<span>{escape(label)}</span><span class="ms">{escape(ms)}</span></div>')
    _html('<div class="panel" style="padding:.6rem .9rem">' + "".join(rows) + "</div>")
