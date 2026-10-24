# file: app/analytics/bridge.py
from __future__ import annotations

from itertools import combinations
from math import factorial

import numpy as np
import pandas as pd

from app.analytics.baseline import Baseline, fit_baseline

FACTORS = ("volume", "mix", "weather", "waste")


def shapley(f, a: dict, b: dict) -> dict:
    """Exact Shapley attribution of f(b) - f(a) to each factor (keys of a/b are f's keyword args)."""
    names = list(a)
    n = len(names)
    out = {k: 0.0 for k in names}
    for k in names:
        others = [x for x in names if x != k]
        for r in range(n):
            w = factorial(r) * factorial(n - r - 1) / factorial(n)
            for subset in combinations(others, r):
                base = {x: (b[x] if x in subset else a[x]) for x in names}
                out[k] += w * (f(**{**base, k: b[k]}) - f(**base))
    return out


def round_preserving_sum(values: dict, nd: int = 1) -> dict:
    """Largest-remainder rounding: rounded parts add up to the rounded total."""
    scale = 10 ** nd
    total = round(sum(values.values()) * scale)
    floors = {k: int(np.floor(v * scale)) for k, v in values.items()}
    rest = sorted(values, key=lambda k: -(values[k] * scale - floors[k]))
    for k in rest[: int(total - sum(floors.values()))]:
        floors[k] += 1
    return {k: v / scale for k, v in floors.items()}


def _totals(daily: pd.DataFrame, products: list[str]) -> dict:
    units = {p: float(daily[f"units_{p}"].sum()) for p in products}
    vol = sum(units.values())
    return {"n_days": len(daily), "n_nonprod": float(daily["nonprod"].sum()), "V": vol,
            "shares": {p: (units[p] / vol if vol else 0.0) for p in products},
            "cdd": float(daily["cooling_degree_days"].sum()), "hdd": float(daily["heating_degree_days"].sum()),
            "E": float(daily["kwh"].sum()), "C": float(daily["cost"].sum())}


def bill_bridge(daily_a: pd.DataFrame, daily_b: pd.DataFrame, products: list[str],
                baseline: Baseline | None = None) -> dict:
    features = [f"units_{p}" for p in products] + ["cooling_degree_days", "heating_degree_days", "nonprod"]
    base = baseline or fit_baseline(daily_a, features)
    c = base.coef
    ta, tb = _totals(daily_a, products), _totals(daily_b, products)

    def energy(volume, mix, weather, waste):
        n_days, n_nonprod, vol = volume
        cdd, hdd = weather
        return (c["const"] * n_days + c["nonprod"] * n_nonprod
                + vol * sum(c[f"units_{p}"] * mix[p] for p in products)
                + c["cooling_degree_days"] * cdd + c["heating_degree_days"] * hdd + waste)

    def factors(t):
        return {"volume": (t["n_days"], t["n_nonprod"], t["V"]), "mix": t["shares"], "weather": (t["cdd"], t["hdd"])}

    fa, fb = factors(ta), factors(tb)
    fa["waste"] = ta["E"] - energy(**fa, waste=0.0)
    fb["waste"] = tb["E"] - energy(**fb, waste=0.0)
    phi = shapley(energy, fa, fb)                              # kWh, sums to E_B - E_A
    pa, pb = ta["C"] / ta["E"], tb["C"] / tb["E"]
    money = {"tariff": (pb - pa) * (ta["E"] + tb["E"]) / 2, **{k: v * (pa + pb) / 2 for k, v in phi.items()}}
    pct = {k: 100 * v / ta["C"] for k, v in money.items()}
    total_pct = 100 * (tb["C"] - ta["C"]) / ta["C"]
    return {"total_change_pct": total_pct, "components_pct": pct, "components_money": money,
            "components_kwh": phi, "sum_check_pct": sum(pct.values()) - total_pct,
            "avg_price": {"a": pa, "b": pb}, "energy_kwh": {"a": ta["E"], "b": tb["E"]},
            "cost": {"a": ta["C"], "b": tb["C"]},
            "baseline": {"r2": base.r2, "cv_rmse": base.cv_rmse, "n_days": base.n, "coef": base.coef},
            "waste_kwh": {"a": fa["waste"], "b": fb["waste"]}}


def bridge_ranges(daily_a: pd.DataFrame, daily_b: pd.DataFrame, products: list[str], n_boot: int = 200,
                  seed: int = 7, data_quality_share: float = 0.0) -> dict:
    """5th–95th percentile per component from a weekly block bootstrap of the baseline period.
    Tariff is exact given the data; widen it (and all parts) by the imputed-data share."""
    features = [f"units_{p}" for p in products] + ["cooling_degree_days", "heating_degree_days", "nonprod"]
    weeks = pd.to_datetime(pd.Series(daily_a.index)).dt.to_period("W").to_numpy()
    blocks = [daily_a[weeks == w] for w in pd.unique(weeks)]
    rng = np.random.default_rng(seed)
    draws: dict[str, list[float]] = {}
    for _ in range(n_boot):
        sample = pd.concat([blocks[i] for i in rng.integers(0, len(blocks), len(blocks))])
        res = bill_bridge(daily_a, daily_b, products, baseline=fit_baseline(sample, features))
        for k, v in res["components_pct"].items():
            draws.setdefault(k, []).append(v)
    out = {}
    for k, v in draws.items():
        lo, hi = float(np.percentile(v, 5)), float(np.percentile(v, 95))
        pad = abs(np.median(v)) * data_quality_share
        out[k] = [lo - pad, hi + pad]
    return out


def to_contract(bridge: dict, ranges: dict, order=("tariff", "product_mix", "volume", "weather", "waste")) -> list[dict]:
    """Shape for the response 'bridge' list. Rename keys to the statement's cause names."""
    names = {"mix": "product_mix"}
    pct = {names.get(k, k): v for k, v in bridge["components_pct"].items()}
    rng = {names.get(k, k): v for k, v in ranges.items()}
    shown = round_preserving_sum(pct, 1)
    return [{"cause": k, "pct_points": shown[k],
             "range": [round(min(rng[k][0], pct[k]), 1), round(max(rng[k][1], pct[k]), 1)]} for k in order]
