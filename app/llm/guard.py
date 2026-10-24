# file: app/llm/guard.py
"""Number-faithfulness guard: every number/ISO date in LLM prose must come from FACTS or the question."""
from __future__ import annotations

import math
import re
from typing import Any, Iterable

_DATE = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b")
_CURRENCY = re.compile(r"(?:\bRs\.?|\bINR\b|\bUSD\b|\bEUR\b|₹|\$|€|£)\s*", re.I)
_UNIT_SPLIT = re.compile(
    r"(?<=\d)(?=(?:kwh|mwh|gwh|kw|mw|kg|t|x|k|mn|bn|cr|pp|pts|days?|hrs?|h|yrs?|months?|mins?|ms|s)\b)", re.I)
_RUN = re.compile(r"[A-Za-z0-9_/\-]+(?:\.\d+)*")
_LIST_MARKER = re.compile(r"(?m)^\s*(?:\d{1,2}[.)]|[-*•])\s+")
_ORDINAL_REF = re.compile(r"\b(?:step|option|phase|#)\s*\d+\b", re.I)
_GROUPED = r"(?:\d{1,3}(?:,\d{3})+|\d{1,2}(?:,\d{2})+,\d{3}|\d+)(?:\.\d+)?"
_NUM = re.compile(r"(?<![\w.])(-?" + _GROUPED + r")(?![\w])(\s?%)?"
                  r"(?:\s?(thousand|k|lakhs?|crores?|cr|million|mn|billion|bn)\b)?", re.I)
_NUM_LOOSE = re.compile(r"-?" + _GROUPED)
_MAGNITUDE = {"thousand": 1e3, "k": 1e3, "lakh": 1e5, "lakhs": 1e5, "crore": 1e7, "crores": 1e7,
              "cr": 1e7, "million": 1e6, "mn": 1e6, "billion": 1e9, "bn": 1e9}


def _sig(x: float, digits: int) -> float:
    return 0.0 if x == 0 else round(x, -int(math.floor(math.log10(abs(x)))) + (digits - 1))


def _variants(a: float) -> set[float]:
    out: set[float] = set()
    for x in (a, abs(a)):
        out.update({x, round(x), round(x, 1), round(x, 2), round(x, 3), _sig(x, 2), _sig(x, 3)})
        if abs(x) <= 1.5:  # fraction written as a percentage
            out.update({x * 100, round(x * 100), round(x * 100, 1), round(x * 100, 2)})
    return {round(v, 6) for v in out}


def _numbers_in(obj: Any) -> Iterable[float]:
    if isinstance(obj, bool) or obj is None:
        return
    if isinstance(obj, (int, float)):
        if math.isfinite(obj):
            yield float(obj)
    elif isinstance(obj, str):
        for m in _DATE.finditer(obj):
            yield from (float(g) for g in m.groups())
        for m in _NUM_LOOSE.finditer(obj):
            yield float(m.group(0).replace(",", ""))
    elif isinstance(obj, dict):
        for v in obj.values():
            yield from _numbers_in(v)
    elif isinstance(obj, (list, tuple, set)):
        for v in obj:
            yield from _numbers_in(v)


def _dates_in(obj: Any) -> set[str]:
    if isinstance(obj, str):
        return {m.group(0) for m in _DATE.finditer(obj)}
    if isinstance(obj, dict):
        return set().union(*(_dates_in(v) for v in obj.values())) if obj else set()
    if isinstance(obj, (list, tuple, set)):
        return set().union(*(_dates_in(v) for v in obj)) if obj else set()
    return set()


def allowed_numbers(facts: Any, question: str = "") -> set[float]:
    allowed: set[float] = set()
    for value in list(_numbers_in(facts)) + list(_numbers_in(question)):
        allowed |= _variants(value)
    return allowed


def check_faithfulness(text: str, facts: Any, question: str = "") -> dict:
    allowed = allowed_numbers(facts, question)
    allowed_dates = _dates_in(facts) | _dates_in(question)
    unsupported: list[str] = []
    checked = 0
    t = (text or "").replace("−", "-").replace("–", " – ")
    for m in _DATE.finditer(t):
        checked += 1
        if m.group(0) not in allowed_dates:
            unsupported.append(m.group(0))
    t = _DATE.sub(" ", t)
    t = _LIST_MARKER.sub(" ", t)
    t = _ORDINAL_REF.sub(" ", t)
    t = _CURRENCY.sub(" ", t)
    t = _UNIT_SPLIT.sub(" ", t)
    t = _RUN.sub(lambda m: " " if re.search(r"[A-Za-z]", m.group(0)) and re.search(r"\d", m.group(0))
                 else m.group(0), t)
    for m in _NUM.finditer(t):
        checked += 1
        value = float(m.group(1).replace(",", ""))
        candidates = {value}
        if m.group(2):
            candidates.add(value / 100)
        if m.group(3):
            candidates.add(value * _MAGNITUDE[m.group(3).lower()])
        if not any(round(c, 6) in allowed for c in candidates):
            unsupported.append(m.group(0).strip())
    return {"ok": not unsupported, "unsupported": unsupported, "checked": checked}
