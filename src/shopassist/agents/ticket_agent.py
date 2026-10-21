"""Agent 3: Ticket & Resolution. Records the case and prepares the proposal."""
from src.shopassist import database
from src.shopassist.graph.tracing import traced, use
from src.shopassist.tools.ticket_tools import create_ticket, update_ticket_status


@traced("ticket_agent")
def ticket_agent(state, thread_id):
    order, result, action = state["order"], state["policy_result"], state["action"]
    priority = "High" if order["amount"] >= 2000 or "damaged" in state["message"].lower() else "Medium"

    ticket = use(create_ticket, thread_id, customer_id=state["customer_id"], order_id=order["order_id"],
                 category=action, priority=priority, description=state["message"], requested_action=action,
                 thread_id=thread_id, findings={"order": order, "policy": result})
    ticket_id = ticket["ticket_id"]

    # Audit trail: what the other two agents found
    database.log_event(thread_id, ticket_id, "order_agent", "info",
                       f"Order retrieved: {order['order_status']}, amount {order['amount']}", kind="audit")
    database.log_event(thread_id, ticket_id, "policy_agent", "info", f"Eligibility checked: {result['reason']}", kind="audit")

    if result["requires_approval"]:
        use(update_ticket_status, thread_id, ticket_id=ticket_id, status="AWAITING_APPROVAL",
            note="Eligible; support approval requested")
        database.log_event(thread_id, ticket_id, "approval", "waiting", "Workflow checkpointed - waiting for human approval")
        text = (f"Your request has been recorded as ticket {ticket_id}. It is awaiting support approval. "
                f"No {action} has been executed yet.")
    else:
        use(update_ticket_status, thread_id, ticket_id=ticket_id, status="IN_PROGRESS", note="Approved automatically by policy")
        text = f"Ticket {ticket_id} created. Processing your {action} now."
    return {"ticket_id": ticket_id, "response": text, "event_msg": f"created {ticket_id}"}
