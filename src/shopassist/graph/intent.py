"""Intent classification: an LLM chain (prompt | llm | parser) with keyword rules as the offline fallback."""
import os
import re
from typing import Literal

from langchain_core.output_parsers import PydanticOutputParser
from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel

from src.shopassist import config

INTENTS = ["order_status", "policy_question", "refund", "return", "replacement",
           "cancellation", "existing_ticket", "other"]


class IntentResult(BaseModel):
    intent: Literal["order_status", "policy_question", "refund", "return", "replacement",
                    "cancellation", "existing_ticket", "other"]


INTENT_PROMPT = ChatPromptTemplate.from_messages([
    ("system",
     "You classify messages sent to an e-commerce support assistant. Choose exactly one intent:\n"
     "- order_status: asking where an order is or whether it was delivered\n"
     "- policy_question: asking about a policy in general, not about a specific order\n"
     "- refund: wants money back for an order\n"
     "- return: wants to send an item back\n"
     "- replacement: wants a damaged or defective item replaced\n"
     "- cancellation: wants to cancel an order\n"
     "- existing_ticket: asking about a support ticket\n"
     "- other: anything else, including greetings\n\n{format_instructions}"),
    ("human", "{message}"),
])


def keyword_intent(message: str) -> str:
    """Simple rules. Fast and free, but they miss unusual wording."""
    text = message.lower()
    if "policy" in text or "policies" in text: return "policy_question"
    if "tkt-" in text or "ticket" in text: return "existing_ticket"
    if "cancel" in text: return "cancellation"
    if "refund" in text or "money back" in text: return "refund"
    if "replace" in text or "damaged" in text or "defective" in text: return "replacement"
    if "return" in text: return "return"
    if any(word in text for word in ("where", "track", "status", "deliver", "arriv")): return "order_status"
    return "other"


def get_llm():
    if not os.getenv("GROQ_API_KEY"):
        raise RuntimeError("GROQ_API_KEY is not set. Add it to the .env file.")
    from langchain_groq import ChatGroq
    return ChatGroq(model=config.LLM_MODEL, temperature=0)


def llm_intent(message: str, llm=None) -> str:
    parser = PydanticOutputParser(pydantic_object=IntentResult)
    prompt = INTENT_PROMPT.partial(format_instructions=parser.get_format_instructions())
    chain = (prompt | (llm or get_llm()) | parser).with_retry(stop_after_attempt=2)
    return chain.invoke({"message": message}).intent


def classify(message: str, mode: str = "auto", llm=None) -> str:
    """mode: 'keyword' = rules only, 'llm' = LLM only (errors are raised), 'auto' = LLM if a key exists, else rules."""
    if mode == "keyword" or (mode == "auto" and llm is None and not os.getenv("GROQ_API_KEY")):
        return keyword_intent(message)
    try:
        return llm_intent(message, llm)
    except Exception:
        if mode == "llm":
            raise
        return keyword_intent(message)


def find_order_id(message: str) -> str | None:
    match = re.search(r"ORD\d+", message, re.I)
    return match.group().upper() if match else None


def find_ticket_id(message: str) -> str | None:
    match = re.search(r"TKT-\d+", message, re.I)
    return match.group().upper() if match else None
