"""Backend-only actions. These are deliberately NOT LLM tools: the graph calls them only after approval."""
from src.shopassist import database


class TransientError(Exception):
    """A temporary failure that is worth retrying."""


FAILURES = {"remaining": 0}  # demo switch: make the next N executions fail


def execute_resolution(ticket_id: str, action: str) -> dict:
    """Simulated refund / return / replacement / cancellation. Safe to call twice: it never repeats the action."""
    action_id = f"{ticket_id}:{action}"
    if database.query("SELECT 1 FROM actions WHERE action_id=? AND status='DONE'", (action_id,), one=True):
        return {"action_id": action_id, "status": "DONE", "already_done": True}

    if FAILURES["remaining"] > 0:
        FAILURES["remaining"] -= 1
        raise TransientError("Payment gateway timeout (simulated)")

    ticket = database.query("SELECT order_id FROM tickets WHERE ticket_id=?", (ticket_id,), one=True)
    database.run("INSERT OR REPLACE INTO actions VALUES (?,?,?,?,?,?)",
                 (action_id, ticket_id, action, "DONE", "simulated", database.now()))
    if action == "cancellation":
        database.run("UPDATE orders SET order_status='CANCELLED', tracking_status='Cancelled' WHERE order_id=?",
                     (ticket["order_id"],))
    return {"action_id": action_id, "status": "DONE"}


def verify_resolution(ticket_id: str, action: str) -> bool:
    """Check that the action really was recorded, instead of trusting the call that did it."""
    return bool(database.query("SELECT 1 FROM actions WHERE action_id=? AND status='DONE'",
                               (f"{ticket_id}:{action}",), one=True))
