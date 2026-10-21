"""The functions the API, the demo script and the evaluation all share: chat, decide, and ticket lookups."""
import json
import logging
import time

from langgraph.types import Command

from src.shopassist import database
from src.shopassist.graph.workflow import build_workflow

logger = logging.getLogger("shopassist")


class TicketNotFound(LookupError):
    pass


class ApprovalError(ValueError):
    """The ticket is not waiting for a decision (already decided, or never needed one)."""


def create_workflow(checkpoint_path: str | None = None):
    """Make sure the database exists and compile the graph."""
    database.init_db()
    return build_workflow(checkpoint_path)


def thread_id_for(customer_id: str, session_id: str) -> str:
    """One conversation = one thread. The checkpointer saves and resumes state by this id."""
    return f"{customer_id}-{session_id}"


def chat(workflow, customer_id: str, message: str, session_id: str = "s1", intent_mode: str = "auto") -> dict:
    """Run one customer message through the graph."""
    thread_id = thread_id_for(customer_id, session_id)
    config = {"configurable": {"thread_id": thread_id}}

    snapshot = workflow.get_state(config)
    if snapshot.next:  # Rule: while a ticket awaits approval, the customer only gets a status reply
        ticket_id = snapshot.values.get("ticket_id")
        return {"thread_id": thread_id, "ticket_id": ticket_id, "waiting": True, "steps": [],
                "response": f"Ticket {ticket_id} is still awaiting support approval. I'll update you here once it's decided."}

    last_event = database.query("SELECT COALESCE(MAX(id),0) AS m FROM events", one=True)["m"]
    start = time.perf_counter()
    workflow.invoke({"customer_id": customer_id, "message": message, "intent_mode": intent_mode}, config)

    snapshot = workflow.get_state(config)
    steps = database.query("SELECT node FROM events WHERE id>? AND thread_id=? AND status='completed' ORDER BY id",
                           (last_event, thread_id))
    logger.info("intent=%s | waiting=%s | %.2fs | message=%s", snapshot.values.get("intent"), bool(snapshot.next),
                time.perf_counter() - start, message)
    return {"thread_id": thread_id, "response": snapshot.values["response"], "ticket_id": snapshot.values.get("ticket_id"),
            "waiting": bool(snapshot.next), "intent": snapshot.values.get("intent"), "steps": [s["node"] for s in steps]}


def decide(workflow, ticket_id: str, decision: str, reason: str = "") -> dict:
    """Support's decision. Resumes the paused graph from its checkpoint. decision = 'approve' or 'reject'."""
    ticket = database.query("SELECT * FROM tickets WHERE ticket_id=?", (ticket_id,), one=True)
    if not ticket:
        raise TicketNotFound(f"Ticket {ticket_id} not found")

    config = {"configurable": {"thread_id": ticket["thread_id"]}}
    if ticket["status"] != "AWAITING_APPROVAL" or not workflow.get_state(config).next:
        raise ApprovalError(f"Ticket is {ticket['status']}, not awaiting approval")

    workflow.invoke(Command(resume={"decision": decision, "reason": reason}), config)
    return ticket_status(ticket_id)


# ---------- reading tickets (used by the dashboard) ----------
def ticket_status(ticket_id: str) -> dict:
    ticket = database.query("SELECT ticket_id, status, resolution FROM tickets WHERE ticket_id=?", (ticket_id,), one=True)
    if not ticket:
        raise TicketNotFound(f"Ticket {ticket_id} not found")
    return ticket


def get_ticket_details(ticket_id: str) -> dict:
    ticket = database.query("SELECT * FROM tickets WHERE ticket_id=?", (ticket_id,), one=True)
    if not ticket:
        raise TicketNotFound(f"Ticket {ticket_id} not found")
    ticket["findings"] = json.loads(ticket["findings"] or "{}")
    return ticket


def list_tickets(status: str = "", search: str = "") -> dict:
    rows = database.query("SELECT ticket_id, customer_id, order_id, category, priority, status, created_at "
                          "FROM tickets ORDER BY created_at DESC, ticket_id DESC")
    counts: dict[str, int] = {}
    for row in rows:
        counts[row["status"]] = counts.get(row["status"], 0) + 1
    if status:
        rows = [row for row in rows if row["status"] == status]
    if search:
        rows = [row for row in rows if search.lower() in " ".join(str(v) for v in row.values()).lower()]
    return {"tickets": rows, "counts": counts, "total": sum(counts.values())}


def ticket_timeline(ticket_id: str) -> list[dict]:
    return database.query("SELECT * FROM events WHERE ticket_id=? AND kind='audit' ORDER BY id", (ticket_id,))
