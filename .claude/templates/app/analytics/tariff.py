# file: app/analytics/tariff.py
from __future__ import annotations

import numpy as np
import pandas as pd


def check_tariff(tariff: pd.DataFrame, start, end) -> dict:
    t = tariff.copy()
    for c in ("valid_from", "valid_to"):
        t[c] = pd.to_datetime(t[c], utc=True)
    issues = []
    for period, g in t.groupby("period"):
        g = g.sort_values("valid_from")
        prev_end = g["valid_to"].shift()
        if (g["valid_from"] < prev_end).any():
            issues.append(f"{period}: overlapping rows")
        if (g["valid_from"] > prev_end).iloc[1:].any():
            issues.append(f"{period}: gap between rows")
    if t["valid_from"].min() > pd.Timestamp(start, tz="UTC") or t["valid_to"].max() < pd.Timestamp(end, tz="UTC"):
        issues.append("tariff does not cover the whole analysis period")
    return {"ok": not issues, "issues": issues, "price_changes": int(t["price_per_kwh"].diff().fillna(0).ne(0).sum())}


def price_intervals(meter: pd.DataFrame, tariff: pd.DataFrame, tou_windows: dict | None = None,
                    tz: str = "UTC") -> pd.DataFrame:
    """meter: ts, kwh (one meter, usually main). Returns rows with price_per_kwh and cost (NaN = uncovered)."""
    t = tariff.copy()
    for c in ("valid_from", "valid_to"):
        t[c] = pd.to_datetime(t[c], utc=True).astype("datetime64[ns, UTC]")
    m = meter.copy()
    m["ts"] = pd.to_datetime(m["ts"], utc=True).astype("datetime64[ns, UTC]")
    by = None
    if tou_windows:  # e.g. {"peak": [(18, 22)], "off_peak": [(22, 24), (0, 6)], "standard": [(6, 18)]}
        hours = m["ts"].dt.tz_convert(tz).dt.hour
        m["period"] = None
        for period, spans in tou_windows.items():
            for lo, hi in spans:
                m.loc[(hours >= lo) & (hours < hi), "period"] = period
        by = "period"
    j = pd.merge_asof(m.sort_values("ts"), t.sort_values("valid_from"), left_on="ts", right_on="valid_from",
                      by=by, direction="backward")
    j.loc[j["ts"] >= j["valid_to"], "price_per_kwh"] = np.nan
    j["cost"] = j["kwh"] * j["price_per_kwh"]
    return j
