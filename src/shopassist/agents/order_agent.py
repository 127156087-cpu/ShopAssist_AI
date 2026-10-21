"""Agent 1: Order & Delivery. Answers 'what actually happened to this order?'. It reports facts only."""
from src.shopassist.graph.tracing import traced, use
from src.shopassist.tools.order_tools import check_cancellation_status, get_order, get_tracking_status


@traced("order_agent")
def order_agent(state, thread_id):
    order_id = state["order_id"]
    order = use(get_order, thread_id, order_id=order_id, customer_id=state["customer_id"])
    if "error" in order:
        return {"response": f"Sorry, {order['error']}.", "event_msg": "order not found"}

    tracking = use(get_tracking_status, thread_id, order_id=order_id)
    update = {"order": order, "event_msg": f"order is {order['order_status']}"}

    if state["intent"] == "cancellation":
        update["order"]["can_cancel"] = use(check_cancellation_status, thread_id, order_id=order_id)["can_cancel"]

    if state["intent"] == "order_status":  # a plain status question ends here: no policy check, no ticket
        text = f"Your order {order_id} ({order['product_name']}) is {order['order_status'].lower()}. Tracking: {tracking['tracking_status']}."
        if tracking.get("estimated_delivery"):
            text += f" Estimated delivery: {tracking['estimated_delivery']}."
        update["response"] = text
    return update
