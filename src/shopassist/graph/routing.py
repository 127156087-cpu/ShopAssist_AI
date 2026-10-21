"""Conditional edges: each function looks at the state and returns the name of the next node."""
from src.shopassist import config


def route_intake(state):
    intent = state["intent"]
    if intent == "other":
        return "ask_info"
    if intent == "existing_ticket":
        return "ticket_lookup" if state.get("ticket_ref") else "ask_info"
    if intent == "policy_question":
        return "policy_agent"
    return "order_agent" if state.get("order_id") else "ask_info"


def after_order(state):
    return "respond" if state.get("response") else "policy_agent"      # a status answer or an error ends the turn


def after_policy(state):
    return "respond" if state.get("response") else "ticket_agent"      # a policy answer or "not eligible" ends the turn


def after_ticket(state):
    return "approval" if state["policy_result"]["requires_approval"] else "execute"


def after_approval(state):
    return "execute" if state["approved"] else "respond"


def after_execute(state):
    """The retry loop: try again until MAX_ATTEMPTS, then give up and record the failure."""
    if state.get("execution"):
        return "verify"
    return "execute" if state["attempts"] < config.MAX_ATTEMPTS else "record_failure"


def after_verify(state):
    return "finish" if state["verified"] else "record_failure"
