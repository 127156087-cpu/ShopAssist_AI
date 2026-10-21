"""Tools for the Order & Delivery agent. They report facts; they never change anything."""
from langchain_core.tools import tool

from src.shopassist import database


@tool
def get_order(order_id: str, customer_id: str) -> dict:
    """Retrieve an order. Only the customer who owns it can see it."""
    order = database.query("SELECT * FROM orders WHERE order_id=? AND customer_id=?", (order_id, customer_id), one=True)
    return order or {"error": f"order {order_id} was not found on your account"}


@tool
def get_tracking_status(order_id: str) -> dict:
    """Retrieve the tracking status and estimated delivery date."""
    row = database.query("SELECT tracking_status, estimated_delivery FROM orders WHERE order_id=?", (order_id,), one=True)
    return row or {"error": "order not found"}


@tool
def check_cancellation_status(order_id: str) -> dict:
    """An order can only be cancelled while it is still PLACED."""
    row = database.query("SELECT order_status FROM orders WHERE order_id=?", (order_id,), one=True)
    return {"can_cancel": bool(row and row["order_status"] == "PLACED")}
