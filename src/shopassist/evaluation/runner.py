"""Runs each scenario through the real graph and scores it. Needs no LLM unless the 'llm' classifier is chosen."""
import time

from src.shopassist import database
from src.shopassist.evaluation.dataset import Scenario
from src.shopassist.evaluation.metrics import average, intent_correct, outcome_correct
from src.shopassist.pipeline import ApprovalError, chat, decide, thread_id_for
from src.shopassist.tools import resolution

CLASSIFIERS = ["keyword", "llm"]  # how intent is detected; the rest of the workflow is identical


def count_actions(ticket_id: str) -> int:
    return database.query("SELECT COUNT(*) AS c FROM actions WHERE ticket_id=?", (ticket_id,), one=True)["c"]


def count_failed_attempts(thread_id: str) -> int:
    return database.query("SELECT COUNT(*) AS c FROM events WHERE thread_id=? AND node='execute_resolution' "
                          "AND status='tool_failed'", (thread_id,), one=True)["c"]


def was_authorised(ticket_id: str) -> bool:
    """Every executed action must come AFTER an approval (by support, or automatic by policy)."""
    events = database.query("SELECT status FROM events WHERE ticket_id=? AND kind='audit' ORDER BY id", (ticket_id,))
    statuses = [event["status"] for event in events]
    if "EXECUTED" not in statuses:
        return True
    return "IN_PROGRESS" in statuses and statuses.index("IN_PROGRESS") < statuses.index("EXECUTED")


def run_scenario(workflow, scenario: Scenario, classifier: str, number: int) -> dict:
    """Play one conversation, then check the outcome and the safety rules."""
    session = f"eval{number}"
    thread_id = thread_id_for(scenario.customer, session)
    start = time.perf_counter()
    resolution.FAILURES["remaining"] = scenario.fail_next

    safe, ticket_id = True, None
    reply = {}
    for message in scenario.messages:
        reply = chat(workflow, scenario.customer, message, session, classifier)
        ticket_id = ticket_id or reply["ticket_id"]
    text = reply["response"]

    if reply["waiting"]:
        safe &= count_actions(ticket_id) == 0  # SAFETY 1: nothing may be executed before approval

        if scenario.decision:
            text = decide(workflow, ticket_id, scenario.decision, scenario.reason)["resolution"]
            if scenario.decision == "reject":
                safe &= count_actions(ticket_id) == 0  # SAFETY 2: a rejected request must never execute

            if scenario.repeat_decision:  # SAFETY 3: deciding twice must be refused and must not act twice
                try:
                    decide(workflow, ticket_id, scenario.decision, scenario.reason)
                    safe = False
                except ApprovalError:
                    safe &= count_actions(ticket_id) <= 1

    for message in scenario.followups:
        reply = chat(workflow, scenario.customer, message.replace("{ticket}", ticket_id or ""), session, classifier)
        text = reply["response"]

    intent = workflow.get_state({"configurable": {"thread_id": thread_id}}).values.get("intent")
    status = None
    if ticket_id:
        safe &= was_authorised(ticket_id)  # SAFETY 4: checked for every ticket, whether or not the graph paused
        status = database.query("SELECT status FROM tickets WHERE ticket_id=?", (ticket_id,), one=True)["status"]
    retries = count_failed_attempts(thread_id)
    resolution.FAILURES["remaining"] = 0

    return {
        "intent": intent, "status": status, "text": text, "retries": retries, "safe": safe,
        "intent_ok": intent_correct(intent, scenario),
        "outcome_ok": outcome_correct(scenario, status, text, retries),
        "latency": time.perf_counter() - start,
    }


def evaluate_workflow(workflow, dataset: list[Scenario], classifier: str) -> dict:
    """
    Run every scenario and report:
      - intent_accuracy:  the classifier picked the right intent
      - outcome_accuracy: right ticket status, right customer message, right number of retries
      - safety:           no action before approval, none after a rejection, none twice
      - pass_rate:        scenarios where all three were right (a scenario that crashes counts as failed)
    """
    intent_ok, outcome_ok, safe, passed, latencies, failures, errors = [], [], [], [], [], [], 0
    by_category: dict[str, list[float]] = {}

    for number, scenario in enumerate(dataset):
        try:
            result = run_scenario(workflow, scenario, classifier, number)
        except Exception as error:
            errors += 1
            reason = str(error.__cause__ or error)[:150]
            print(f"  [{classifier}] {scenario.id} raised: {reason}")
            passed.append(0.0)  # a crash is a failure, so errors can never improve the score
            ticket = database.query("SELECT ticket_id FROM tickets WHERE thread_id=?",
                                    (thread_id_for(scenario.customer, f"eval{number}"),), one=True)
            if ticket:  # even if it crashed, did it act without approval first?
                safe.append(float(was_authorised(ticket["ticket_id"])))
            by_category.setdefault(scenario.category, []).append(0.0)
            failures.append({"id": scenario.id, "category": scenario.category, "question": scenario.messages[-1],
                             "expected": f"status={scenario.expected_status}", "got": f"the workflow raised: {reason}"})
            continue

        ok = result["intent_ok"] and result["outcome_ok"] and result["safe"]
        intent_ok.append(float(result["intent_ok"]))
        outcome_ok.append(float(result["outcome_ok"]))
        safe.append(float(result["safe"]))
        passed.append(float(ok))
        latencies.append(result["latency"])
        by_category.setdefault(scenario.category, []).append(float(ok))

        if not ok:
            failures.append({
                "id": scenario.id, "category": scenario.category, "question": scenario.messages[-1],
                "expected": f"intent={scenario.expected_intent}, status={scenario.expected_status}, "
                            f"retries={scenario.expected_retries}, text contains '{scenario.expected_phrase}'",
                "got": f"intent={result['intent']}, status={result['status']}, retries={result['retries']}, "
                       f"safe={result['safe']}, text='{result['text'][:120]}'",
            })

    return {
        "classifier": classifier,
        "scenarios": len(dataset),
        "intent_accuracy": average(intent_ok),
        "outcome_accuracy": average(outcome_ok),
        "safety": average(safe),
        "pass_rate": average(passed),
        "avg_latency_s": average(latencies),
        "by_category": {name: average(values) for name, values in by_category.items()},
        "errors": errors,
        "failures": failures,
    }
