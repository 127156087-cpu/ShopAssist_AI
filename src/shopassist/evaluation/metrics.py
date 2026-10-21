from src.shopassist.evaluation.dataset import Scenario


def normalise(text: str) -> str:
    """Lowercase and collapse whitespace, so formatting differences don't hide a match."""
    return " ".join(text.lower().split())


def average(values: list[float]) -> float | None:
    return sum(values) / len(values) if values else None


def intent_correct(actual: str | None, scenario: Scenario) -> bool:
    """Did the classifier pick the right intent for the last message?"""
    return actual == scenario.expected_intent


def outcome_correct(scenario: Scenario, status: str | None, text: str, retries: int) -> bool:
    """Right ticket status, right message to the customer, and the expected number of retries."""
    return (
        status == scenario.expected_status
        and normalise(scenario.expected_phrase) in normalise(text)
        and retries == scenario.expected_retries
    )
