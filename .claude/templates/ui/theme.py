# file: ui/theme.py
"""Design tokens + CSS injection. Call inject_theme() right after st.set_page_config()."""
import streamlit as st

TOKENS = {
    "ink": "#0E1726", "ink2": "#16233A", "text": "#E8EEF6", "muted": "#9AA8BC", "accent": "#3FB8AF",
    "line": "rgba(232,238,246,0.12)", "glass": "rgba(255,255,255,0.06)",
}
ANSWER_COLORS = {
    "retrieved_fact": "#3FB8AF", "calculated": "#5AA9FF", "not_found": "#94A3B8", "not_in_data": "#94A3B8",
    "clarification_needed": "#F2B33D", "refused": "#F2665E", "conflict_flagged": "#A58BFF",
    "decomposition": "#58D68D", "recommendation": "#F5A962",
}
FONT_HEAD = "'Bricolage Grotesque', 'Segoe UI', system-ui, sans-serif"
FONT_BODY = "'Manrope', 'Segoe UI', system-ui, -apple-system, sans-serif"

CSS = f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Bricolage+Grotesque:opsz,wght@12..96,500;12..96,700&family=Manrope:wght@400;500;600&display=swap');
:root {{ --ink:{TOKENS['ink']}; --ink2:{TOKENS['ink2']}; --text:{TOKENS['text']}; --muted:{TOKENS['muted']};
        --accent:{TOKENS['accent']}; --line:{TOKENS['line']}; --glass:{TOKENS['glass']}; }}
/* hide Streamlit chrome but keep the sidebar toggle usable */
#MainMenu, footer, [data-testid="stToolbar"], [data-testid="stDecoration"], [data-testid="stStatusWidget"] {{ visibility:hidden; height:0; }}
header[data-testid="stHeader"] {{ background:transparent; }}
[data-testid="stAppViewContainer"] {{
  background: radial-gradient(1200px 600px at 85% -10%, rgba(63,184,175,0.10), transparent 60%),
              linear-gradient(160deg, var(--ink) 0%, var(--ink2) 100%);
  color: var(--text); font-family:{FONT_BODY}; font-variant-numeric: tabular-nums; }}
[data-testid="stSidebar"] > div {{ background: rgba(14,23,38,0.72); backdrop-filter: blur(10px); border-right:1px solid var(--line); }}
.block-container {{ padding-top: 1.6rem; max-width: 1380px; }}
h1, h2, h3 {{ font-family:{FONT_HEAD}; letter-spacing:-0.01em; }}
.hero h1 {{ font-size: clamp(1.8rem, 2.6vw, 2.6rem); margin:0; }}
.hero p {{ color: var(--muted); margin:.2rem 0 1rem 0; }}
/* glass panels: bordered containers + our HTML cards */
[data-testid="stVerticalBlockBorderWrapper"], .panel {{
  background: var(--glass); backdrop-filter: blur(14px); -webkit-backdrop-filter: blur(14px);
  border: 1px solid var(--line) !important; border-radius: 16px; }}
.answer-card {{ background: linear-gradient(180deg, rgba(255,255,255,0.09), rgba(255,255,255,0.04));
  border:1px solid var(--line); border-radius:22px; padding:1.2rem 1.4rem; box-shadow: 0 18px 40px rgba(0,0,0,0.28); }}
.answer-card .text {{ font-size:1.12rem; line-height:1.55; margin:.6rem 0 .2rem 0; max-width: 72ch; }}
.answer-card .expl {{ color: var(--muted); font-size:.95rem; line-height:1.5; max-width: 76ch; }}
.badge {{ display:inline-block; padding:.18rem .62rem; border-radius:999px; font-size:.78rem; font-weight:600;
  border:1px solid currentColor; background: rgba(255,255,255,0.04); }}
.chips {{ display:flex; flex-wrap:wrap; gap:.4rem; margin:.7rem 0; }}
.chip {{ padding:.28rem .7rem; border-radius:999px; border:1px solid var(--line); font-size:.82rem; color:var(--text);
  background: rgba(255,255,255,0.03); text-decoration:none; }}
.chip:hover {{ border-color: var(--accent); }}
.bento {{ display:grid; grid-template-columns: repeat(auto-fit, minmax(170px, 1fr)); gap:.7rem; margin:.6rem 0 1rem; }}
.tile {{ background: var(--glass); border:1px solid var(--line); border-radius:12px; padding:.75rem .9rem; }}
.tile .label {{ color: var(--muted); font-size:.8rem; }}
.tile .value {{ font-family:{FONT_HEAD}; font-size:1.45rem; font-weight:700; }}
.tile .sub {{ color: var(--muted); font-size:.78rem; }}
.pill {{ display:inline-flex; align-items:center; gap:.35rem; margin:.15rem .3rem .15rem 0; font-size:.82rem; }}
.dot {{ width:.55rem; height:.55rem; border-radius:50%; display:inline-block; }}
.step {{ display:grid; grid-template-columns: 1.2rem 1fr auto; gap:.5rem; padding:.35rem 0; border-bottom:1px dashed var(--line); font-size:.88rem; }}
.step .ms {{ color: var(--muted); }}
.stButton > button[kind="primary"] {{ background: var(--accent); color:#06201E; border:0; font-weight:600; }}
:focus-visible {{ outline: 2px solid var(--accent) !important; outline-offset: 2px; }}
@media (prefers-reduced-motion: reduce) {{ * {{ transition:none !important; animation:none !important; }} }}
</style>
"""


def inject_theme() -> None:
    st.markdown(CSS, unsafe_allow_html=True)
