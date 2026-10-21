import json
from pathlib import Path

from pydantic import BaseModel

from src.shopassist.config import EVAL_DATASET_PATH


class Scenario(BaseModel):
    """One test conversation, with what should happen at the end."""

    id: str
    category: str                      # e.g. order_status | refund | ineligible | memory | security | retry
    customer: str = "C101"
    messages: list[str]                # what the customer says, in order
    decision: str | None = None        # "approve" or "reject", applied if the workflow pauses for approval
    reason: str = ""                   # reason given when rejecting
    repeat_decision: bool = False      # try to decide a second time (must be refused)
    fail_next: int = 0                 # make the next N simulated executions fail (tests the retry loop)
    followups: list[str] = []          # messages sent after the decision; {ticket} = the ticket created earlier
    expected_intent: str               # intent of the LAST message
    expected_status: str | None = None # final status of the ticket; None = no ticket should exist
    expected_phrase: str               # must appear in the final text the customer sees
    expected_retries: int = 0          # how many failed execution attempts we expect to see


def load_dataset(path: Path = EVAL_DATASET_PATH) -> list[Scenario]:
    """Read the evaluation scenarios from a JSON file."""
    items = json.loads(Path(path).read_text(encoding="utf-8"))
    return [Scenario(**item) for item in items]
