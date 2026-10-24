# file: app/analytics/clean.py
"""Resample to a regular UTC grid, drop duplicates, neutralise negatives and reset spikes, fill short gaps."""
from __future__ import annotations

import numpy as np
import pandas as pd


def clean_intervals(df: pd.DataFrame, freq: str = "15min", max_fill: int = 4,
                    spike_factor: float = 5.0) -> tuple[pd.DataFrame, dict]:
    d = df[["meter_id", "ts", "kwh"]].copy()
    d["ts"] = pd.to_datetime(d["ts"], utc=True).astype("datetime64[ns, UTC]")
    d["kwh"] = pd.to_numeric(d["kwh"], errors="coerce").astype(float)
    rep: dict = {"rows_in": len(d)}
    dup = d.duplicated(["meter_id", "ts"], keep="last")
    rep["duplicates_dropped"] = int(dup.sum())
    d = d[~dup].copy()
    neg = d["kwh"] < 0
    rep["negative_set_missing"] = int(neg.sum())
    d.loc[neg, "kwh"] = np.nan
    q995 = d.groupby("meter_id")["kwh"].transform(lambda s: s.quantile(0.995)).clip(lower=1e-9)
    spike = d["kwh"] > spike_factor * q995          # meter resets / rollovers show up as huge jumps
    rep["spikes_set_missing"] = int(spike.sum())
    d.loc[spike, "kwh"] = np.nan
    grid = pd.date_range(d["ts"].min().floor(freq), d["ts"].max().floor(freq), freq=freq).astype("datetime64[ns, UTC]")
    parts, gaps = [], {}
    for meter, g in d.groupby("meter_id"):
        s = g.set_index("ts")["kwh"].resample(freq).sum(min_count=1).reindex(grid)
        filled = s.interpolate(limit=max_fill, limit_area="inside")
        gaps[meter] = {"missing": int(s.isna().sum()), "filled": int(s.isna().sum() - filled.isna().sum()),
                       "left_missing": int(filled.isna().sum())}
        parts.append(pd.DataFrame({"meter_id": meter, "ts": grid, "kwh": filled.to_numpy()}))
    rep["gaps_by_meter"] = gaps
    return pd.concat(parts, ignore_index=True), rep


def reconcile(clean: pd.DataFrame, main: str = "main", tolerance: float = 0.05) -> dict:
    """Sub-meters rarely sum to the main meter. Report the unmetered share; bill on the main meter."""
    wide = clean.pivot_table(index="ts", columns="meter_id", values="kwh", aggfunc="sum")
    subs = [c for c in wide.columns if c != main]
    main_kwh, sub_kwh = float(wide[main].sum()), float(wide[subs].sum().sum())
    share = (main_kwh - sub_kwh) / main_kwh if main_kwh else 0.0
    return {"main_kwh": round(main_kwh, 1), "submeters_kwh": round(sub_kwh, 1),
            "unmetered_kwh": round(main_kwh - sub_kwh, 1), "unmetered_share": round(share, 4),
            "within_tolerance": abs(share) <= tolerance, "tolerance": tolerance}


def asset_breakdown(clean: pd.DataFrame, main: str = "main") -> list[dict]:
    """Top users with share of the main meter (capability: 'which assets use the most energy?')."""
    tot = clean.groupby("meter_id")["kwh"].sum()
    main_kwh = float(tot.get(main, tot.drop(main, errors="ignore").sum()))
    rows = [{"asset": m, "kwh": round(float(v), 1), "share_of_main": round(float(v) / main_kwh, 4)}
            for m, v in tot.drop(main, errors="ignore").sort_values(ascending=False).items()]
    return rows
