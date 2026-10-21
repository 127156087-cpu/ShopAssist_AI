"""Tools for the Ticket & Resolution agent."""
import json

from langchain_core.tools import tool

from src.shopassist import database

# Allowed status changes. Enforced here in code, so the LLM can never jump a ticket to RESOLVED.
TRANSITIONS = {
    "OPEN": {"AWAITING_APPROVAL", "IN_PROGRESS"},
    "AWAITING_APPROVAL": {"IN_PROGRESS", "REJECTED"},
    "IN_PROGRESS": {"RESOLVED", "FAILED"},
    "FAILED": {"IN_PROGRESS"},
}


@tool
def create_ticket(customer_id: str, order_id: str, category: str, priority: str, description: str,
                  requested_action: str, thread_id: str, findings: dict) -> dict:
    """Create and save a support ticket."""
    count = database.query("SELECT COUNT(*) AS c FROM tickets", one=True)["c"]
    ticket_id = f"TKT-{1001 + count}"
    database.run("INSERT INTO tickets VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                 (ticket_id, customer_id, order_id, thread_id, category, priority, description, requested_action,
                  json.dumps(findings, default=str), "OPEN", "", database.now(), database.now()))
    database.log_event(thread_id, ticket_id, "ticket", "OPEN", f"Ticket created ({category}, {priority} priority)", kind="audit")
    return {"ticket_id": ticket_id}


@tool
def get_ticket(ticket_id: str, customer_id: str) -> dict:
    """Retrieve a ticket. Only its owner can see it."""
    ticket = database.query("SELECT * FROM tickets WHERE ticket_id=? AND customer_id=?", (ticket_id, customer_id), one=True)
    return ticket or {"error": f"ticket {ticket_id} was not found on your account"}


@tool
def update_ticket_status(ticket_id: str, status: str, note: str, resolution: str = "") -> dict:
    """Record an allowed ticket status change."""
    ticket = database.query("SELECT * FROM tickets WHERE ticket_id=?", (ticket_id,), one=True)
    if status not in TRANSITIONS.get(ticket["status"], set()):
        raise ValueError(f"Invalid transition {ticket['status']} -> {status}")
    database.run(
        "UPDATE tickets SET status=?, resolution=CASE WHEN ?<>'' THEN ? ELSE resolution END, updated_at=? WHERE ticket_id=?",
        (status, resolution, resolution, database.now(), ticket_id))
    database.log_event(ticket["thread_id"], ticket_id, "ticket", status, f"{ticket['status']} -> {status}: {note}", kind="audit")
    return {"ticket_id": ticket_id, "status": status}


@tool
def get_ticket_history(ticket_id: str) -> list:
    """Retrieve the saved timeline of a ticket."""
    return database.query("SELECT created_at, status, message FROM events WHERE ticket_id=? AND kind='audit' ORDER BY id", (ticket_id,))
