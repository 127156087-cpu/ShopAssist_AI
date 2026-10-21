"""Agent 2: Policy & Eligibility. Answers 'is this allowed under our rules?'."""
from src.shopassist.graph.tracing import traced, use
from src.shopassist.tools.policy_tools import check_eligibility, get_policy


def policy_category(message: str) -> str:
    text = message.lower()
    return next((name for name in ("refund", "replacement", "cancellation") if name[:6] in text), "return")


@traced("policy_agent")
def policy_agent(state, thread_id):
    if state["intent"] == "policy_question":  # explain the policy; nothing else to do
        category = policy_category(state["message"])
        policy = use(get_policy, thread_id, category=category)
        return {"response": f"Our {category} policy: {policy['rule_description']}", "event_msg": f"explained {category} policy"}

    action, order_id = state["intent"], state["order_id"]
    use(get_policy, thread_id, category=action)
    result = use(check_eligibility, thread_id, order_id=order_id, action=action)
    update = {"policy_result": result, "action": action, "event_msg": f"eligible={result['eligible']}"}

    if not result["eligible"]:
        update["response"] = (f"I'm sorry, your {action} request for {order_id} can't be processed: {result['reason']}. "
                              "No ticket was created and no action was taken.")
    return update
