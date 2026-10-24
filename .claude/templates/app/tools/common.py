# file: app/tools/common.py
from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from typing import Any


def D(x: Any) -> Decimal:
    return x if isinstance(x, Decimal) else Decimal(str(x))


def money(x: Any) -> float:
    return float(D(x).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def as_date(value: Any, default: date | None = None) -> date:
    if value in (None, ""):
        if default is None:
            raise ValueError("as_of date required")
        return default
    return value if isinstance(value, date) else date.fromisoformat(str(value)[:10])


def add_months(d: date, months: int) -> date:
    y, m = divmod(d.month - 1 + months, 12)
    year, month = d.year + y, m + 1
    return date(year, month, min(d.day, calendar.monthrange(year, month)[1]))


def merge_states(*parts: dict) -> dict:
    """Combine Resolution.to_state() dicts from several get_rule calls."""
    out: dict[str, list] = {"rules_applied": [], "conflicts": [], "assumptions": [], "precedence_decisions": []}
    for p in parts:
        for k in out:
            out[k].extend(p.get(k, []))
    return out


@dataclass(frozen=True)
class Range:
    """[low, high] with honest propagation. Use for savings, CO2e, payback, bridge components."""
    low: float
    high: float

    def __post_init__(self):
        if self.low > self.high:
            object.__setattr__(self, "low", self.high)
            object.__setattr__(self, "high", self.low)

    @property
    def mid(self) -> float:
        return (self.low + self.high) / 2

    def __add__(self, o: "Range") -> "Range":
        return Range(self.low + o.low, self.high + o.high)

    def __mul__(self, o: "Range | float") -> "Range":
        o = o if isinstance(o, Range) else Range(o, o)
        prods = [self.low * o.low, self.low * o.high, self.high * o.low, self.high * o.high]
        return Range(min(prods), max(prods))

    def rounded(self, nd: int = 0) -> list[float]:
        return [round(self.low, nd), round(self.high, nd)]


def payback_months(capex: Range, annual_saving: Range) -> Range:
    """Best case = cheapest capex / biggest saving; worst = dearest capex / smallest saving."""
    if annual_saving.low <= 0:
        return Range(float("inf"), float("inf"))
    return Range(12 * capex.low / annual_saving.high, 12 * capex.high / annual_saving.low)


EASE_ORDER = {"easy": 0, "medium": 1, "hard": 2}


def rank_actions(actions: list[dict]) -> list[dict]:
    """Payback first (conservative = high end), then ease, then bigger saving. Deterministic tie-break on name."""
    return sorted(actions, key=lambda a: (a["payback_months"][1], EASE_ORDER.get(a.get("ease", "medium"), 1),
                                          -a["saving_money_per_year"][1], a["action"]))
