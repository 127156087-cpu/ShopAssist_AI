import operator
from typing import Annotated, TypedDict


class State(TypedDict, total=False):
    """The shared graph state. Agents talk to each other only by writing to and reading from it."""

    customer_id: str
    message: str
    intent_mode: str       # "auto" | "keyword" | "llm"
    order_id: str          # kept between turns = short-term memory ("can I return it?")
    pending_intent: str    # what we were doing when we had to ask for an order ID
    ticket_ref: str        # a ticket ID mentioned by the customer
    intent: str
    order: dict            # written by the Order agent
    policy_result: dict    # written by the Policy agent
    action: str
    ticket_id: str         # written by the Ticket agent
    approved: bool
    execution: dict
    verified: bool
    attempts: int
    response: str          # the text shown to the customer
    messages: Annotated[list, operator.add]   # reducer: the conversation accumulates
    trace: Annotated[list, operator.add]      # reducer: which nodes ran
