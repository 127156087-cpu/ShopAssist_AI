"""Tools for the Policy & Eligibility agent. Eligibility is plain Python: the LLM never decides it."""
from datetime import date

from langchain_core.tools import tool

from src.shopassist import database

ACTIONS = ("refund", "return", "replacement", "cancellation")


@tool
def get_policy(category: str) -> dict:
    """Retrieve the policy for refund, return, replacement or cancellation."""
    return database.query("SELECT * FROM policies WHERE category=?", (category,), one=True) or {"error": "no such policy"}


@tool
def check_eligibility(order_id: str, action: str) -> dict:
    """Check the requested action against the order's state and the policy rules."""
    order = database.query("SELECT * FROM orders WHERE order_id=?", (order_id,), one=True)
    policy = database.query("SELECT * FROM policies WHERE category=?", (action,), one=True)
    if not order or not policy:
        return {"eligible": False, "reason": "Order or policy not found", "requires_approval": False}

    if action == "cancellation":
        eligible = order["order_status"] == "PLACED"
        reason = "Order has not shipped yet" if eligible else f"Order is already {order['order_status'].lower()}"
    elif order["order_status"] != "DELIVERED":
        eligible, reason = False, f"Order is {order['order_status'].lower()}, not delivered"
    else:
        days = (date.today() - date.fromisoformat(order["delivery_date"])).days
        window = policy["return_window_days"]
        eligible = days <= window
        reason = f"Delivered {days} days ago, {'within' if eligible else 'outside'} the {window}-day window"

    return {"eligible": eligible, "reason": reason, "requires_approval": bool(policy["approval_required"]) and eligible}
