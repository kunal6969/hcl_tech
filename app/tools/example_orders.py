# file: app/tools/example_orders.py
"""Pattern tools: scoped lookup, eligibility, refund breakdown, warranty, idempotent return creation."""
from __future__ import annotations

from datetime import date, timedelta

from pydantic import BaseModel, Field

from app.data.db import connect
from app.data.registry import get_rule
from app.tools.common import D, add_months, as_date, merge_states, money
from app.tools.registry import ToolContext, ToolSpec, register

NOT_YOURS = "no such order on this account"   # identical for 'other customer' and 'does not exist'

ITEM_SQL = """
SELECT o.order_id, o.status, o.order_date, c.tier, i.sku, i.qty, i.net_unit_price, i.delivered_on,
       p.name, p.category, p.price AS list_price, p.warranty_months
FROM orders o JOIN customers c ON c.customer_id = o.customer_id
JOIN order_items i ON i.order_id = o.order_id JOIN products p ON p.sku = i.sku
WHERE o.order_id = ? AND o.customer_id = ?
"""


def scoped_items(order_id: str, ctx: ToolContext) -> list[dict]:
    conn = connect()
    cur = conn.execute(ITEM_SQL, (order_id, ctx.principal["subject_id"]))
    cols = [d[0] for d in cur.description]
    rows = [dict(zip(cols, r, strict=True)) for r in cur.fetchall()]
    if not rows:
        raise PermissionError(NOT_YOURS)
    return rows


def pick_item(rows: list[dict], sku: str | None) -> dict | None:
    if sku:
        return next((r for r in rows if r["sku"].upper() == sku.upper()), None)
    return rows[0] if len(rows) == 1 else None


class ItemRef(BaseModel):
    order_id: str
    sku: str | None = Field(None, description="needed when the order has several items")
    assume_days_since_delivery: int | None = Field(None, description="what-if: pretend this many days passed")
    assume_tier: str | None = Field(None, description="what-if: pretend the customer had this tier")


def check_return_eligibility(args: ItemRef, ctx: ToolContext) -> dict:
    rows = scoped_items(args.order_id, ctx)
    item = pick_item(rows, args.sku)
    if item is None:
        return {"needs_clarification": "Which item from this order do you mean?",
                "options": [f"{r['sku']} ({r['name']})" for r in rows]}
    as_of = as_date(ctx.as_of, date.today())
    tier = (args.assume_tier or item["tier"]).upper()
    assumptions = [f"What-if tier: {tier}."] if args.assume_tier else []
    if item["status"] != "DELIVERED" or not item["delivered_on"]:
        return {"result": "NOT_DELIVERED", "reason_code": "NOT_DELIVERED", "order_status": item["status"],
                "assumptions": assumptions}
    window = get_rule(connect(), "return_window_days", as_of, item["category"], tier)
    if window.status == "unresolved":
        return {"result": "UNRESOLVED", "unresolved": True, **window.to_state()}
    delivered = as_date(item["delivered_on"])
    days = args.assume_days_since_delivery
    if days is None:
        days = (as_of - delivered).days
    else:
        assumptions.append(f"What-if: {days} days since delivery.")
    window_days = int(window.value)
    ok = 0 <= days <= window_days
    return {"result": "ELIGIBLE" if ok else "NOT_ELIGIBLE",
            "reason_code": "WITHIN_WINDOW" if ok else "WINDOW_EXPIRED",
            "order_id": item["order_id"], "sku": item["sku"], "category": item["category"], "tier": tier,
            "delivered_on": delivered.isoformat(), "days_since_delivery": days, "window_days": window_days,
            "last_day_to_return": (delivered + timedelta(days=window_days)).isoformat(),
            **merge_states(window.to_state(), {"assumptions": assumptions})}


def calculate_refund(args: ItemRef, ctx: ToolContext) -> dict:
    rows = scoped_items(args.order_id, ctx)
    item = pick_item(rows, args.sku)
    if item is None:
        return {"needs_clarification": "Which item should I calculate the refund for?",
                "options": [f"{r['sku']} ({r['name']})" for r in rows]}
    as_of = as_date(ctx.as_of, date.today())
    tier = (args.assume_tier or item["tier"]).upper()
    conn = connect()
    fee = get_rule(conn, "restocking_fee_pct", as_of, item["category"], tier)
    ship = get_rule(conn, "reverse_shipping_fee", as_of, item["category"], tier)
    limit = get_rule(conn, "auto_refund_limit", as_of, item["category"], tier)
    gross = D(item["net_unit_price"]) * D(item["qty"])          # discounts already in net price
    restocking = gross * D(fee.value)
    refund = max(D(0), gross - restocking - D(ship.value))
    return {"order_id": item["order_id"], "sku": item["sku"], "gross_amount": money(gross),
            "restocking_fee": money(restocking), "restocking_fee_pct": float(fee.value),
            "reverse_shipping_fee": money(ship.value), "refund_amount": money(refund),
            "requires_human_approval": refund > D(limit.value), "approval_limit": money(limit.value),
            **merge_states(fee.to_state(), ship.to_state(), limit.to_state())}


def check_warranty(args: ItemRef, ctx: ToolContext) -> dict:
    item = pick_item(scoped_items(args.order_id, ctx), args.sku)
    if item is None:
        return {"needs_clarification": "Which item's warranty should I check?"}
    if not item["delivered_on"]:
        return {"result": "NOT_DELIVERED", "reason_code": "NOT_DELIVERED"}
    as_of = as_date(ctx.as_of, date.today())
    months = int(item["warranty_months"] or 0)
    expires = add_months(as_date(item["delivered_on"]), months)
    valid = months > 0 and as_of <= expires
    return {"result": "IN_WARRANTY" if valid else ("NO_WARRANTY" if months == 0 else "EXPIRED"),
            "warranty_months": months, "warranty_expires_on": expires.isoformat(),
            "days_remaining": max(0, (expires - as_of).days)}


def create_return(args: ItemRef, ctx: ToolContext) -> dict:
    """State-changing: re-checks eligibility itself, idempotent on (order_id, sku)."""
    check = check_return_eligibility(ItemRef(order_id=args.order_id, sku=args.sku), ctx)
    if check.get("result") != "ELIGIBLE":
        return {"created": False, "eligibility": check.get("result"), "reason_code": check.get("reason_code")}
    conn = connect()
    with conn:  # one transaction
        existing = conn.execute("SELECT return_id, status FROM returns WHERE order_id = ? AND sku = ? "
                                "AND status != 'REJECTED'", (check["order_id"], check["sku"])).fetchone()
        if existing:
            return {"created": False, "already_exists": True, "return_id": existing[0], "status": existing[1]}
        n = conn.execute("SELECT COUNT(*) FROM returns").fetchone()[0] + 1
        return_id = f"R-{n:06d}"
        conn.execute("INSERT INTO returns (return_id, order_id, sku, requested_on, reason, status) "
                     "VALUES (?, ?, ?, ?, ?, 'REQUESTED')",
                     (return_id, check["order_id"], check["sku"], as_date(ctx.as_of, date.today()).isoformat(),
                      "CHANGED_MIND"))
    return {"created": True, "return_id": return_id, "status": "REQUESTED",
            "assumptions": ["Reason not stated: recorded as CHANGED_MIND."]}


for name, fn, desc, mutates in [
    ("check_return_eligibility", check_return_eligibility, "is this delivered item still returnable (window rule)", False),
    ("calculate_refund", calculate_refund, "refund breakdown for an item: gross, fees, refund, approval flag", False),
    ("check_warranty", check_warranty, "warranty status and expiry date for an item", False),
    ("create_return", create_return, "raise a return request after re-checking eligibility (idempotent)", True),
]:
    register(ToolSpec(name, desc, ItemRef, fn, needs_identity=True, mutates_state=mutates))
