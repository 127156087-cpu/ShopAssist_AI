"""Command-line demo: a refund request that pauses for approval, then resumes. Works without any API key."""
import logging

from src.shopassist import database
from src.shopassist.pipeline import chat, create_workflow, decide, ticket_timeline

logging.basicConfig(level=logging.WARNING)

QUESTIONS = [
    "Where is order ORD1024?",
    "What is your return policy?",
    "Refund order ORD1025",
]


def main():
    workflow = create_workflow("data/db/demo_checkpoints.db")
    session = "demo"

    for number, question in enumerate(QUESTIONS):
        reply = chat(workflow, "C101", question, f"{session}-q{number}")
        print(f"\nCustomer: {question}\nAssistant: {reply['response']}\nGraph path: {' -> '.join(reply['steps'])}")

    print("\n" + "=" * 60 + "\nRefund request (needs approval)")
    reply = chat(workflow, "C101", "I received a damaged product. I want a refund for order ORD1024.", session)
    print(f"Assistant: {reply['response']}\nGraph path: {' -> '.join(reply['steps'])}")
    print(f"Paused: {reply['waiting']}  (ticket {reply['ticket_id']})")

    input("\nPress Enter to approve as support...")
    result = decide(workflow, reply["ticket_id"], "approve")
    print(f"Status: {result['status']}\nCustomer is told: {result['resolution']}")

    print("\nTicket timeline:")
    for event in ticket_timeline(reply["ticket_id"]):
        print(f"  {event['status']:<18} {event['message']}")


if __name__ == "__main__":
    main()
