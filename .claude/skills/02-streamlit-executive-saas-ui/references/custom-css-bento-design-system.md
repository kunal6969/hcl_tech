# Design system: "Signal Room" glass bento for Streamlit

A deliberate look for evidence-heavy dashboards: deep ink background, frosted panels with hierarchy
(the answer card is the hero; tiles and chips are quieter), one accent (verdigris) for action, and
semantic colours reserved for answer types. Typography carries personality: a characterful grotesque
for headings, a calm humanist sans for body, tabular figures for every number.

Adapt the accent to the problem's world at S6 (e.g. energy → amber/ember on ink; retail service →
verdigris on ink). Change tokens, not CSS rules.

## Tokens

| Token | Value | Use |
|---|---|---|
| `ink` | `#0E1726` | page background base |
| `ink-2` | `#16233A` | gradient end, sidebar |
| `glass` | `rgba(255,255,255,0.06)` + `blur(14px)` | panels |
| `line` | `rgba(232,238,246,0.12)` | hairlines, borders |
| `text` / `muted` | `#E8EEF6` / `#9AA8BC` | body / secondary (both ≥ 4.5:1 on ink) |
| `accent` | `#3FB8AF` | primary buttons, focus ring, active tab |
| answer types | retrieved `#3FB8AF` · calculated `#5AA9FF` · not_found `#94A3B8` · clarification `#F2B33D` · refused `#F2665E` · conflict `#A58BFF` · decomposition `#58D68D` · recommendation `#F5A962` | badges only |

Radius by hierarchy: hero 22px, panels 16px, tiles 12px, chips 999px. Shadow only on the hero.

## theme.py

**`ui/theme.py`** — design tokens + CSS injection (61 lines). Installed by `python .claude/bootstrap.py`; source: `.claude/templates/ui/theme.py`. Read it only when you need to edit it.

Selector notes (verify once against the installed Streamlit version with the browser inspector):
`stToolbar`, `stDecoration`, `stHeader`, `stSidebar`, `stAppViewContainer` and
`stVerticalBlockBorderWrapper` are `data-testid` hooks; if one changes, only that rule stops applying.
Newer Streamlit adds `key`-based classes: `st.container(border=True, key="hero")` renders a
`.st-key-hero` class you can style precisely. Don't hide the whole header — it holds the sidebar toggle.

## components.py (all untrusted text escaped)

**`ui/components.py`** — answer card, badges, citation chips, KPI tiles, health pills, step timeline (HTML-escaped) (69 lines). Installed by `python .claude/bootstrap.py`; source: `.claude/templates/ui/components.py`. Read it only when you need to edit it.
