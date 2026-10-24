# file: tests/test_analytics.py
import numpy as np
import pandas as pd
import pytest

from app.analytics.anomaly import idle_load, leak_check
from app.analytics.bridge import (
    bill_bridge,
    bridge_ranges,
    round_preserving_sum,
    to_contract,
)
from app.analytics.clean import clean_intervals, reconcile
from app.analytics.savings import leak_action
from app.analytics.tariff import check_tariff, price_intervals
from app.tools.common import Range

WASTE_KWH_PER_DAY = 300.0


def _period(days, ux, uy, cdd_mean, waste, price, rng):
    n = len(days)
    weekend = days.dayofweek >= 5
    units_x = np.where(weekend, 0, rng.uniform(ux[0], ux[1], n)).round()
    units_y = np.where(weekend, 0, rng.uniform(uy[0], uy[1], n)).round()
    cdd = np.clip(rng.normal(cdd_mean, 2.0, n), 0, None)
    kwh = 800 - 300 * weekend + 2.0 * units_x + 3.5 * units_y + 40 * cdd + waste + rng.normal(0, 15, n)
    p = np.array([price(d) for d in days])
    return pd.DataFrame({"kwh": kwh, "cost": kwh * p, "units_x": units_x, "units_y": units_y,
                         "cooling_degree_days": cdd, "heating_degree_days": 0.0,
                         "nonprod": weekend.astype(int)}, index=[d.date() for d in days])


@pytest.fixture(scope="module")
def periods():
    rng = np.random.default_rng(1)
    a = _period(pd.date_range("2026-04-01", "2026-06-30"), (200, 600), (0, 200), 5, 0.0, lambda d: 8.0, rng)
    b = _period(pd.date_range("2026-07-01", "2026-09-30"), (200, 560), (100, 300), 9, WASTE_KWH_PER_DAY,
                lambda d: 9.0 if d >= pd.Timestamp("2026-08-15") else 8.0, rng)
    return a, b


def test_bridge_adds_up_exactly_and_finds_planted_effects(periods):
    a, b = periods
    br = bill_bridge(a, b, ["x", "y"])
    assert abs(br["sum_check_pct"]) < 1e-9
    pct = br["components_pct"]
    true_waste_pct = 100 * WASTE_KWH_PER_DAY * len(b) * sum(br["avg_price"].values()) / 2 / br["cost"]["a"]
    assert pct["waste"] == pytest.approx(true_waste_pct, rel=0.25)
    assert pct["tariff"] > 0 and pct["mix"] > 0 and pct["weather"] > 0
    assert br["baseline"]["r2"] > 0.95


def test_ranges_contain_estimates_and_display_sums(periods):
    a, b = periods
    br = bill_bridge(a, b, ["x", "y"])
    rows = to_contract(br, bridge_ranges(a, b, ["x", "y"], n_boot=40))
    assert round(sum(r["pct_points"] for r in rows), 1) == round(br["total_change_pct"], 1)
    assert all(r["range"][0] <= r["pct_points"] <= r["range"][1] + 0.05 for r in rows)
    assert round_preserving_sum({"a": 8.14, "b": 3.37, "c": 1.24, "d": 0.86, "e": 1.39}) == \
        {"a": 8.1, "b": 3.4, "c": 1.2, "d": 0.9, "e": 1.4}


def _meter(start, days, idle_kw, prod_kw=100.0):
    ts = pd.date_range(start, periods=days * 96, freq="15min", tz="UTC")
    prod = (ts.hour >= 6) & (ts.hour < 22) & (ts.dayofweek < 5)
    return pd.DataFrame({"meter_id": "compressors", "ts": ts, "kwh": np.where(prod, prod_kw, idle_kw) * 0.25})


def test_cleaning_handles_duplicates_negatives_spikes_and_gaps():
    m = _meter("2026-07-01", 2, 15.0)
    m = pd.concat([m, m.iloc[[10]]])                     # duplicate
    m.loc[m.index[20], "kwh"] = -5                       # negative
    m.loc[m.index[30], "kwh"] = 9_999                    # reset spike
    m = m.drop(m.index[40:42])                           # 2-interval gap
    clean, rep = clean_intervals(m)
    assert rep["duplicates_dropped"] == 1 and rep["negative_set_missing"] == 1 and rep["spikes_set_missing"] == 1
    assert clean["kwh"].isna().sum() == 0 and len(clean) == 2 * 96


def test_idle_leak_signature_and_savings_range():
    ref, cur = _meter("2026-04-06", 14, 15.0), _meter("2026-07-06", 14, 45.0)
    weekends = {d.date(): True for m in (ref, cur) for d in m["ts"] if d.dayofweek >= 5}
    ia, ib = idle_load(ref, weekends), idle_load(cur, weekends)
    leak = leak_check(ia, ib)
    assert leak["flag"] and leak["idle_ratio_current"] == pytest.approx(0.45)
    rec = leak_action(leak["excess_idle_kw"], leak["idle_hours_current"], 14, Range(8, 9), 0.4, Range(30000, 60000))
    lo, hi = rec["saving_money_per_year"]
    assert 0 < lo < hi and rec["payback_months"][0] < rec["payback_months"][1]
    assert not leak_check(ia, ia)["flag"]


def test_tariff_mid_period_change_and_coverage():
    tariff = pd.DataFrame({"valid_from": ["2026-07-01", "2026-08-15"], "valid_to": ["2026-08-15", "2026-10-01"],
                           "period": ["flat", "flat"], "price_per_kwh": [8.0, 9.0]})
    assert check_tariff(tariff, "2026-07-01", "2026-09-30")["ok"]
    meter = pd.DataFrame({"ts": ["2026-08-14T23:45:00Z", "2026-08-15T00:00:00Z"], "kwh": [10.0, 10.0]})
    priced = price_intervals(meter, tariff)
    assert priced["cost"].tolist() == [80.0, 90.0]


def test_reconciliation_reports_unmetered_share():
    ts = pd.date_range("2026-07-01", periods=4, freq="15min", tz="UTC")
    df = pd.DataFrame({"meter_id": ["main"] * 4 + ["a"] * 4 + ["b"] * 4, "ts": list(ts) * 3,
                       "kwh": [10.0] * 4 + [6.0] * 4 + [3.5] * 4})
    rec = reconcile(df)
    assert rec["unmetered_share"] == 0.05 and rec["within_tolerance"]
