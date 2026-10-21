import asyncio
import json
import re
import subprocess
import sys

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from src.shopassist import database, pipeline
from src.shopassist.config import ROOT_DIR, SUPPORT_ROLE
from src.shopassist.evaluation.dataset import load_dataset
from src.shopassist.evaluation.experiments import load_results
from src.shopassist.tools import resolution

FRONTEND_DIR = ROOT_DIR / "frontend"

app = FastAPI(title="ShopAssist AI")
workflow = pipeline.create_workflow()  # one compiled graph, shared by all requests


class ChatRequest(BaseModel):
    customer_id: str
    message: str


class Decision(BaseModel):
    reason: str = ""


def clean_session(session_id: str) -> str:
    safe_id = re.sub(r"[^A-Za-z0-9_-]", "", session_id)[:40]
    if len(safe_id) < 8:
        raise HTTPException(400, "Missing or invalid session id.")
    return safe_id


# ---------------- customer chat ----------------
@app.get("/api/customers")
def customers():
    return database.query("SELECT customer_id, name FROM customers")


@app.post("/api/chat")
def chat(request: ChatRequest, x_session_id: str = Header("")):
    if not request.message.strip():
        raise HTTPException(400, "Please type a message.")
    if not database.query("SELECT 1 FROM customers WHERE customer_id=?", (request.customer_id,)):
        raise HTTPException(404, "Unknown customer.")
    return pipeline.chat(workflow, request.customer_id, request.message.strip(), clean_session(x_session_id))


# ---------------- tickets (support dashboard) ----------------
@app.get("/api/tickets")
def list_tickets(status: str = "", q: str = ""):
    return pipeline.list_tickets(status, q)


@app.get("/api/tickets/{ticket_id}")
def get_ticket(ticket_id: str):
    try:
        return pipeline.get_ticket_details(ticket_id)
    except pipeline.TicketNotFound as error:
        raise HTTPException(404, str(error))


@app.get("/api/tickets/{ticket_id}/status")
def ticket_status(ticket_id: str):
    try:
        return pipeline.ticket_status(ticket_id)
    except pipeline.TicketNotFound as error:
        raise HTTPException(404, str(error))


@app.get("/api/tickets/{ticket_id}/events")
def ticket_events(ticket_id: str):
    return pipeline.ticket_timeline(ticket_id)


# ---------------- human approval (support role only) ----------------
def decide(ticket_id: str, decision: str, reason: str, role: str):
    if role != SUPPORT_ROLE:  # demo authorisation. A real app would check a login or token here.
        raise HTTPException(403, "Support role required.")
    try:
        return pipeline.decide(workflow, ticket_id, decision, reason)
    except pipeline.TicketNotFound as error:
        raise HTTPException(404, str(error))
    except pipeline.ApprovalError as error:
        raise HTTPException(409, str(error))


@app.post("/api/tickets/{ticket_id}/approve")
def approve(ticket_id: str, body: Decision = Decision(), x_role: str = Header("")):
    return decide(ticket_id, "approve", body.reason, x_role)


@app.post("/api/tickets/{ticket_id}/reject")
def reject(ticket_id: str, body: Decision = Decision(), x_role: str = Header("")):
    return decide(ticket_id, "reject", body.reason, x_role)


# ---------------- live workflow events (Server-Sent Events) ----------------
@app.get("/api/workflows/{thread_id}/stream")
async def stream(thread_id: str, request: Request, after: int = 0):
    async def events():
        last_id = after
        while not await request.is_disconnected():
            rows = database.query("SELECT * FROM events WHERE thread_id=? AND kind='workflow' AND id>? ORDER BY id",
                                  (thread_id, last_id))
            for row in rows:
                last_id = row["id"]
                yield f"data: {json.dumps(row)}\n\n"
            await asyncio.sleep(0.4)
    return StreamingResponse(events(), media_type="text/event-stream")


# ---------------- demo control: make the next executions fail ----------------
@app.post("/api/demo/fail-next")
def fail_next(times: int = 1):
    resolution.FAILURES["remaining"] = max(0, min(times, 10))
    return {"failures_queued": resolution.FAILURES["remaining"]}


# ---------------- evaluation ----------------
@app.get("/api/evaluation")
def evaluation():
    """Scenario count plus whatever run_evaluation.py last saved."""
    return {"scenarios": len(load_dataset()), "saved": load_results()}


@app.post("/api/evaluation/run")
def run_evaluation():
    """Run the keyword evaluation in a separate process, so it uses its own temporary database."""
    process = subprocess.run([sys.executable, str(ROOT_DIR / "run_evaluation.py")], cwd=ROOT_DIR,
                             capture_output=True, text=True, timeout=300)
    if process.returncode != 0:
        raise HTTPException(500, "Evaluation failed: " + process.stderr[-300:])
    return {"scenarios": len(load_dataset()), "saved": load_results()}


# Must come last: serves the HTML/CSS/JS at "/"
app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")
