from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from enum import StrEnum


class ActionKind(StrEnum):
    LOCAL = "local"
    EXTERNAL = "external"
    FINANCIAL = "financial"
    COMMUNICATION = "communication"
    PUBLICATION = "publication"
    AGREEMENT = "agreement"
    ACCOUNT = "account"


@dataclass(frozen=True)
class Opportunity:
    name: str
    summary: str
    startup_cost_cents: int
    expected_return: str
    difficulty: int
    time_required: str
    scalability: int
    competition: int
    risk: int
    time_to_first_revenue: str
    expected_margin: str
    required_skills: list[str]
    automation_fit: int
    legal_platform_constraints: str
    testable_within_budget: bool

    def __post_init__(self) -> None:
        if self.startup_cost_cents < 0:
            raise ValueError("startup cost cannot be negative")
        scores = (
            self.difficulty,
            self.scalability,
            self.competition,
            self.risk,
            self.automation_fit,
        )
        if any(score not in range(1, 6) for score in scores):
            raise ValueError("opportunity scores must be between 1 and 5")


@dataclass(frozen=True)
class ProposedAction:
    description: str
    kind: ActionKind
    reason: str
    expected_upside: str
    risks: str
    cost_cents: int = 0

    def __post_init__(self) -> None:
        if self.cost_cents < 0:
            raise ValueError("action cost cannot be negative")


@dataclass(frozen=True)
class BusinessDecision:
    opportunities: list[Opportunity]
    selected_strategy: str
    rationale: str
    action_plan: list[str]
    next_action: ProposedAction
    lessons_applied: list[str] = field(default_factory=list)
    research_citations: list[int] = field(default_factory=list)
    assumptions: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not 2 <= len(self.opportunities) <= 6:
            raise ValueError("a decision must compare between 2 and 6 opportunities")
        if not 1 <= len(self.action_plan) <= 10:
            raise ValueError("an action plan must contain between 1 and 10 steps")
        names = {item.name for item in self.opportunities}
        if self.selected_strategy not in names:
            raise ValueError("selected_strategy must exactly match an opportunity name")

    def model_dump_json(self) -> str:
        return json.dumps(asdict(self))
