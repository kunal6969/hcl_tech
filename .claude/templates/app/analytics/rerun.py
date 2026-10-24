# file: app/analytics/rerun.py
from __future__ import annotations


def diff_bridges(before: dict, after: dict, threshold: float = 0.05) -> list[dict]:
    """Component-level change in percentage points, largest first. Narrate only what this returns."""
    rows = []
    for k in after["components_pct"]:
        delta = after["components_pct"][k] - before["components_pct"].get(k, 0.0)
        if abs(delta) >= threshold:
            rows.append({"component": k, "before_pct": round(before["components_pct"].get(k, 0.0), 2),
                         "after_pct": round(after["components_pct"][k], 2), "delta_pct_points": round(delta, 2)})
    rows.append({"component": "total", "before_pct": round(before["total_change_pct"], 2),
                 "after_pct": round(after["total_change_pct"], 2),
                 "delta_pct_points": round(after["total_change_pct"] - before["total_change_pct"], 2)})
    return sorted(rows, key=lambda r: -abs(r["delta_pct_points"]) if r["component"] != "total" else 1)
