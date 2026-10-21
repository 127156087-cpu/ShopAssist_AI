"""The workflow nodes that are not agents: intake, approval, execution, verification and responses."""
from langchain_core.runnables import RunnableConfig
from langgraph.types import interrupt

from src.shopassist import config as settings
from src.shopassist import database
from src.shopassist.graph.intent import classify, find_order_id, find_ticket_id
from src.shopassist.graph.tracing import traced, use
from src.shopassist.tools.resolution import TransientError, execute_resolution, verify_resolution
from src.shopassist.tools.ticket_tools import get_ticket, get_ticket_history, update_ticket_status


@traced("intake")
def intake(state, thread_id):
    message = state["message"]
    order_id, ticket_ref = find_order_id(message), find_ticket_id(message)
    intent = classify(message, state.get("intent_mode") or "auto")

    # The customer may just be answering our question ("ORD1025"), so go back to what they were asking for
    if intent == "other" and order_id and state.get("pending_intent"):
        intent = state["pending_intent"]

    return {
        "intent": intent, "pending_intent": None, "ticket_ref": ticket_ref,
        "order_id": order_id or state.get("order_id"),  # kept from earlier turns when not repeated
        # reset everything that belongs to one turn
        "order": None, "policy_result": None, "ticket_id": None, "approved": None, "execution": None,
        "verified": None, "attempts": 0, "response": None, "action": None,
        "messages": [{"role": "user", "content": message}], "event_msg": f"intent = {intent}",
    }


@traced("ask_info")
def ask_info(state, thread_id):
    if state["intent"] == "existing_ticket":
        return {"response": "Please share your ticket ID (for example TKT-1001).", "event_msg": "asked for ticket ID"}
    if state["intent"] == "other":
        return {"response": ("I can help with order status, returns, refunds, replacements, cancellations, "
                             "policies and ticket status. What do you need?"), "event_msg": "asked what they need"}
    return {"response": "Could you share your order ID (for example ORD1024)?",
            "pending_intent": state["intent"], "event_msg": "asked for order ID"}


@traced("ticket_lookup")
def ticket_lookup(state, thread_id):
    ticket = use(get_ticket, thread_id, ticket_id=state["ticket_ref"], customer_id=state["customer_id"])
    if "error" in ticket:
        return {"response": f"Sorry, {ticket['error']}.", "event_msg": "ticket not found"}
    history = use(get_ticket_history, thread_id, ticket_id=ticket["ticket_id"])
    latest = history[-1]["message"] if history else "no updates yet"
    return {"response": f"Ticket {ticket['ticket_id']} ({ticket['category']}) is {ticket['status']}. Latest update: {latest}",
            "event_msg": f"status {ticket['status']}"}


def approval(state, config: RunnableConfig):
    """HUMAN-IN-THE-LOOP. interrupt() saves a checkpoint and stops the graph until Command(resume=...) arrives."""
    thread_id, ticket_id = config["configurable"]["thread_id"], state["ticket_id"]
    decision = interrupt({"ticket_id": ticket_id, "action": state["action"], "ask": "approve or reject"})

    approved = decision.get("decision") == "approve"
    reason = decision.get("reason") or "no reason given"
    database.log_event(thread_id, ticket_id, "approval", "decided", "Approved by support" if approved else f"Rejected: {reason}")

    update = {"approved": approved, "trace": ["approval"]}
    if approved:
        use(update_ticket_status, thread_id, ticket_id=ticket_id, status="IN_PROGRESS", note="Approved by support")
    else:
        text = f"Your {state['action']} request ({ticket_id}) was reviewed and not approved. Reason: {reason}."
        use(update_ticket_status, thread_id, ticket_id=ticket_id, status="REJECTED", note=f"Rejected: {reason}", resolution=text)
        update["response"] = text
    return update


@traced("execute")
def execute(state, thread_id):
    """Run the simulated action. A temporary failure is counted and the graph's routing decides whether to retry."""
    attempts, ticket_id = state.get("attempts") or 0, state["ticket_id"]
    try:
        result = execute_resolution(ticket_id, state["action"])
    except TransientError as error:
        attempts += 1
        database.log_event(thread_id, ticket_id, "execute_resolution", "tool_failed",
                           f"{error} (attempt {attempts}/{settings.MAX_ATTEMPTS})")
        return {"attempts": attempts, "execution": None, "event_msg": f"attempt {attempts} failed"}

    database.log_event(thread_id, ticket_id, "execute_resolution", "tool_ok", f"Simulated {state['action']} executed")
    database.log_event(thread_id, ticket_id, "ticket", "EXECUTED",
                       f"Simulated {state['action']} executed (attempt {attempts + 1})", kind="audit")
    return {"execution": result, "event_msg": "executed"}


@traced("verify")
def verify(state, thread_id):
    ok = verify_resolution(state["ticket_id"], state["action"])
    database.log_event(thread_id, state["ticket_id"], "ticket", "VERIFIED" if ok else "UNVERIFIED",
                       "Result verified in the actions table" if ok else "Could not verify the result", kind="audit")
    return {"verified": ok, "event_msg": f"verified={ok}"}


@traced("finish")
def finish(state, thread_id):
    text = (f"Your {state['action']} for order {state['order_id']} has been processed (simulated) and verified. "
            f"Ticket {state['ticket_id']} is resolved.")
    use(update_ticket_status, thread_id, ticket_id=state["ticket_id"], status="RESOLVED",
        note="Action executed and verified", resolution=text)
    return {"response": text}


@traced("record_failure")
def record_failure(state, thread_id):
    text = (f"We couldn't complete your {state['action']} automatically. Ticket {state['ticket_id']} "
            "has been sent to our support team for manual handling.")
    use(update_ticket_status, thread_id, ticket_id=state["ticket_id"], status="FAILED",
        note="Execution failed after retries", resolution=text)
    return {"response": text}


@traced("respond")
def respond(state, thread_id):
    return {"messages": [{"role": "assistant", "content": state["response"]}], "event_msg": "response ready"}
