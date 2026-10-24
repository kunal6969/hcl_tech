# file: ui/charts.py
"""Plotly figures styled to the theme. Inputs are contract rows; no computation beyond layout."""
from __future__ import annotations

import inspect

import plotly.graph_objects as go
import streamlit as st

INK, TEXT, MUTED, ACCENT, UP, DOWN = "#0E1726", "#E8EEF6", "#9AA8BC", "#3FB8AF", "#F2665E", "#58D68D"
FONT = "Manrope, Segoe UI, system-ui, sans-serif"
_HAS_WIDTH = "width" in inspect.signature(st.plotly_chart).parameters


def apply_theme(fig: go.Figure, title: str = "", height: int = 380) -> go.Figure:
    fig.update_layout(title={"text": title, "x": 0, "font": {"size": 16}}, height=height,
                      paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                      font={"family": FONT, "color": TEXT}, margin={"l": 10, "r": 10, "t": 48, "b": 10},
                      showlegend=False)
    fig.update_xaxes(gridcolor="rgba(232,238,246,0.08)", zeroline=False)
    fig.update_yaxes(gridcolor="rgba(232,238,246,0.08)", zeroline=False)
    return fig


def show_chart(fig: go.Figure, key: str | None = None) -> None:
    """Works across Streamlit versions (width='stretch' replaced use_container_width)."""
    config = {"displayModeBar": False}
    if _HAS_WIDTH:
        st.plotly_chart(fig, width="stretch", key=key, config=config)
    else:
        st.plotly_chart(fig, use_container_width=True, key=key, config=config)


def bridge_waterfall(bridge: list[dict], start_label: str = "Last period", end_label: str = "This period") -> go.Figure:
    """Rows: {"cause", "pct_points", "range"}. Bars in percentage points from 0 to the total change."""
    x = [start_label] + [r["cause"].replace("_", " ").title() for r in bridge] + [end_label]
    y = [0.0] + [r["pct_points"] for r in bridge] + [0.0]
    measure = ["absolute"] + ["relative"] * len(bridge) + ["total"]
    text = [""] + [f"{r['pct_points']:+.1f} pp<br><span style='font-size:11px'>[{r['range'][0]:.1f}, {r['range'][1]:.1f}]</span>"
                   for r in bridge] + [f"{sum(r['pct_points'] for r in bridge):+.1f} pp"]
    fig = go.Figure(go.Waterfall(x=x, y=y, measure=measure, text=text, textposition="outside",
                                 connector={"line": {"color": MUTED, "width": 1}},
                                 increasing={"marker": {"color": UP}}, decreasing={"marker": {"color": DOWN}},
                                 totals={"marker": {"color": ACCENT}}))
    return apply_theme(fig, "What moved the bill (percentage points)")


def ranges_bar(bridge: list[dict]) -> go.Figure:
    """Same causes as horizontal bars with asymmetric uncertainty whiskers."""
    names = [r["cause"].replace("_", " ").title() for r in bridge][::-1]
    vals = [r["pct_points"] for r in bridge][::-1]
    hi = [max(0.0, r["range"][1] - r["pct_points"]) for r in bridge][::-1]
    lo = [max(0.0, r["pct_points"] - r["range"][0]) for r in bridge][::-1]
    fig = go.Figure(go.Bar(x=vals, y=names, orientation="h", marker={"color": ACCENT},
                           error_x={"type": "data", "symmetric": False, "array": hi, "arrayminus": lo,
                                    "color": TEXT, "thickness": 1.2}))
    return apply_theme(fig, "Each cause with its range", height=300)


def pareto(rows: list[dict], label: str = "asset", value: str = "kwh") -> go.Figure:
    rows = sorted(rows, key=lambda r: -r[value])
    total = sum(r[value] for r in rows) or 1
    cum, running = [], 0.0
    for r in rows:
        running += r[value]
        cum.append(100 * running / total)
    fig = go.Figure()
    fig.add_bar(x=[r[label] for r in rows], y=[r[value] for r in rows], marker={"color": ACCENT}, name=value)
    fig.add_scatter(x=[r[label] for r in rows], y=cum, yaxis="y2", mode="lines+markers",
                    line={"color": TEXT}, name="cumulative %")
    fig.update_layout(yaxis2={"overlaying": "y", "side": "right", "range": [0, 105], "ticksuffix": "%",
                              "gridcolor": "rgba(0,0,0,0)"})
    return apply_theme(fig, "Top users (Pareto)")


def load_heatmap(z: list[list[float]], hours: list[int], days: list[str], title: str = "Average kW by hour") -> go.Figure:
    """z[day][hour] prepared by a tool (mean kW). Idle-hour waste shows as a bright band at night."""
    fig = go.Figure(go.Heatmap(z=z, x=hours, y=days, colorscale=[[0, INK], [0.5, "#1F6F78"], [1, "#F5A962"]],
                               colorbar={"title": "kW"}))
    return apply_theme(fig, title, height=320)


def before_after(diff_rows: list[dict]) -> go.Figure:
    """Rows from diff_bridges(): component, before_pct, after_pct, delta_pct_points."""
    rows = [r for r in diff_rows if r["component"] != "total"]
    fig = go.Figure(go.Bar(x=[r["delta_pct_points"] for r in rows], y=[r["component"] for r in rows],
                           orientation="h", marker={"color": [UP if r["delta_pct_points"] > 0 else DOWN for r in rows]},
                           text=[f"{r['before_pct']:.1f} → {r['after_pct']:.1f}" for r in rows], textposition="auto"))
    return apply_theme(fig, "What changed after the new data (pp)", height=300)
