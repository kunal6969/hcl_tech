# file: app/analytics/anomaly.py
from __future__ import annotations

import pandas as pd


def idle_load(clean: pd.DataFrame, nonprod_days: dict, shift_hours: tuple[int, int] = (6, 22),
              tz: str = "UTC", interval_hours: float = 0.25) -> pd.DataFrame:
    """Per meter: idle kWh/hours/kW (outside shift hours or on non-production days) vs production kW."""
    d = clean.dropna(subset=["kwh"]).copy()
    local = d["ts"].dt.tz_convert(tz)
    off_shift = (local.dt.hour < shift_hours[0]) | (local.dt.hour >= shift_hours[1])
    d["idle"] = off_shift | local.dt.date.map(lambda x: bool(nonprod_days.get(x, False)))
    agg = d.groupby(["meter_id", "idle"])["kwh"].agg(["sum", "count"]).unstack(fill_value=0)
    out = pd.DataFrame({
        "idle_kwh": agg[("sum", True)], "prod_kwh": agg[("sum", False)],
        "idle_hours": agg[("count", True)] * interval_hours, "prod_hours": agg[("count", False)] * interval_hours})
    out["idle_kw"] = out["idle_kwh"] / out["idle_hours"].where(out["idle_hours"] > 0)
    out["prod_kw"] = out["prod_kwh"] / out["prod_hours"].where(out["prod_hours"] > 0)
    out["idle_ratio"] = out["idle_kw"] / out["prod_kw"]
    out["idle_share"] = out["idle_kwh"] / (out["idle_kwh"] + out["prod_kwh"])
    return out.round(4)


def leak_check(idle_a: pd.DataFrame, idle_b: pd.DataFrame, meter: str = "compressors",
               ratio_threshold: float = 0.3, min_increase: float = 0.1, floor_ratio: float = 0.1) -> dict:
    """Leak signature: load that persists when nothing is produced, high in absolute terms and rising vs reference."""
    ra, rb = float(idle_a.loc[meter, "idle_ratio"]), float(idle_b.loc[meter, "idle_ratio"])
    flagged = rb >= ratio_threshold and (rb - ra) >= min_increase
    excess_kw = max(0.0, rb - max(ra, floor_ratio)) * float(idle_b.loc[meter, "prod_kw"])
    return {"meter": meter, "flag": flagged, "idle_ratio_reference": round(ra, 3), "idle_ratio_current": round(rb, 3),
            "excess_idle_kw": round(excess_kw, 2), "idle_hours_current": float(idle_b.loc[meter, "idle_hours"]),
            "evidence": f"{meter} idle load is {rb:.0%} of production load vs {ra:.0%} in the reference period"}
