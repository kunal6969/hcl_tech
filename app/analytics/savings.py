# file: app/analytics/savings.py
from __future__ import annotations

from app.tools.common import Range, payback_months, rank_actions

DEFAULT_RECOVERABLE = Range(0.6, 0.9)   # share of excess idle load a repair recovers (assumption: state it)


def leak_action(excess_kw: float, idle_hours_in_period: float, period_days: int, price: Range,
                emission_factor_kg_per_kwh: float, capex: Range, recoverable: Range = DEFAULT_RECOVERABLE,
                action: str = "Repair compressed-air leaks", ease: str = "easy") -> dict:
    hours_per_year = idle_hours_in_period * 365 / period_days
    kwh = Range(excess_kw * hours_per_year, excess_kw * hours_per_year) * recoverable
    money = kwh * price
    co2_t = kwh * (emission_factor_kg_per_kwh / 1000)
    return {"action": action, "saving_kwh_per_year": kwh.rounded(-2), "saving_money_per_year": money.rounded(-2),
            "saving_co2e_t_per_year": co2_t.rounded(1), "payback_months": payback_months(capex, money).rounded(1),
            "ease": ease, "requires_approval": True,
            "assumptions": [f"Recoverable share {recoverable.low:.0%}-{recoverable.high:.0%} of excess idle load",
                            f"Price {price.low}-{price.high} per kWh", f"Capex {capex.low:,.0f}-{capex.high:,.0f}",
                            f"Emission factor {emission_factor_kg_per_kwh} kg CO2e per kWh"]}


def plan(actions: list[dict]) -> list[dict]:
    return rank_actions(actions)
