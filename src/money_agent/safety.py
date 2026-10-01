from __future__ import annotations

import re

from money_agent.models import ActionKind, ProposedAction


PROHIBITED_TERMS = {
    "gamble", "gambling", "casino", "sports betting", "loan", "debt", "leverage",
    "scam", "fraud", "impersonate", "spam", "fake review", "circumvent security",
    "unauthorized access",
}

EXTERNAL_INTENT_PATTERNS = (
    r"\b(?:publish|post|upload|deploy|release)\b",
    r"\b(?:send|contact|outreach)\b|^\s*(?:email|message)\b",
    r"\b(?:purchase|buy|pay|charge|transfer)\b",
    r"\b(?:create|register|open|close|modify|change|delete)\s+(?:(?:a|an|the)\s+)?(?:external\s+)?account\b",
    r"\bsubmit\s+(?:an?\s+)?form\b",
    r"\bmake\s+(?:an?\s+)?http\s+request\b",
)


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
    external_intent = any(
        re.search(pattern, action.description, flags=re.IGNORECASE)
        for pattern in EXTERNAL_INTENT_PATTERNS
    )
    return action.cost_cents > 0 or action.kind != ActionKind.LOCAL or external_intent
