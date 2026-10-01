from __future__ import annotations

from money_agent.models import ActionKind, ProposedAction


PROHIBITED_TERMS = {
    "gamble", "gambling", "casino", "sports betting", "loan", "debt", "leverage",
    "scam", "fraud", "impersonate", "spam", "fake review", "circumvent security",
    "unauthorized access",
}


class SafetyViolation(ValueError):
    pass


def validate_action(action: ProposedAction) -> None:
    normalized = " ".join(
        [action.description, action.reason, action.expected_upside, action.risks]
    ).lower()
    matches = sorted(term for term in PROHIBITED_TERMS if term in normalized)
    if matches:
        raise SafetyViolation(f"prohibited activity detected: {', '.join(matches)}")


def requires_approval(action: ProposedAction) -> bool:
    validate_action(action)
    return action.cost_cents > 0 or action.kind != ActionKind.LOCAL

