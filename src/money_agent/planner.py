from __future__ import annotations

import json
import os
from typing import Protocol

from money_agent.ledger import LedgerSummary
from money_agent.models import ActionKind, BusinessDecision, Opportunity, ProposedAction

OBJECTIVE = "Maximize legitimate REALIZED profit, starting with a simulated $100 budget."

SAFETY_RULES = """Never gamble, bet, borrow, use debt or leverage, scam, defraud, mislead,
impersonate, spam, manipulate reviews, violate platform terms or laws, bypass security, or
access an account without authorization. Projected revenue is never realized revenue. Version 3
can use read-only hosted web search and create only inside its local workspace; it cannot take
external actions. Prefer small, evidence-seeking steps over speculation."""


class Planner(Protocol):
    name: str

    def decide(
        self, ledger: LedgerSummary, memories: list[dict], research: list[dict]
    ) -> BusinessDecision: ...


class OfflinePlanner:
    """Transparent deterministic planner used when no API key is configured."""

    name = "offline rules (no AI API call)"

    def decide(
        self, ledger: LedgerSummary, memories: list[dict], research: list[dict]
    ) -> BusinessDecision:
        return BusinessDecision(
            opportunities=[
                Opportunity(
                    name="Niche digital template pack",
                    summary="Create a focused, useful digital product.",
                    startup_cost_cents=0,
                    expected_return="Unknown; validate demand before projecting sales.",
                    difficulty=2,
                    time_required="1-3 days",
                    scalability=4,
                    competition=4,
                    risk=2,
                    time_to_first_revenue="Unknown until demand is validated",
                    expected_margin="Potentially high digital gross margin; unverified",
                    required_skills=["customer research", "document design"],
                    automation_fit=4,
                    legal_platform_constraints="Respect marketplace terms and intellectual property",
                    testable_within_budget=True,
                ),
                Opportunity(
                    name="Productized spreadsheet service",
                    summary="Offer a narrowly scoped spreadsheet cleanup or dashboard service.",
                    startup_cost_cents=0,
                    expected_return="Unknown; depends on validated customer demand.",
                    difficulty=3,
                    time_required="2-5 days",
                    scalability=2,
                    competition=3,
                    risk=2,
                    time_to_first_revenue="Unknown until outreach is approved",
                    expected_margin="Labor-dependent and unverified",
                    required_skills=["spreadsheets", "requirements analysis"],
                    automation_fit=3,
                    legal_platform_constraints="Customer data would require authorization and privacy controls",
                    testable_within_budget=True,
                ),
                Opportunity(
                    name="Local business checklist",
                    summary="Develop a specialized operations checklist for one business niche.",
                    startup_cost_cents=0,
                    expected_return="Unknown until customer interviews are available.",
                    difficulty=2,
                    time_required="1-2 days",
                    scalability=4,
                    competition=3,
                    risk=2,
                    time_to_first_revenue="Unknown until demand is validated",
                    expected_margin="Potentially high digital gross margin; unverified",
                    required_skills=["research", "technical writing"],
                    automation_fit=4,
                    legal_platform_constraints="Avoid regulated advice and respect intellectual property",
                    testable_within_budget=True,
                ),
            ],
            selected_strategy="Niche digital template pack",
            rationale="It can be prototyped without spending cash, has low downside, and creates a concrete asset whose demand can later be tested. This is a hypothesis, not proof of revenue.",
            action_plan=[
                "Choose one customer niche and painful recurring task",
                "Draft a minimal template",
                "Define a demand-validation experiment",
                "Request approval before any outreach or publication",
                "Measure real outcomes and revise",
            ],
            next_action=ProposedAction(
                description="Draft a private one-page customer/problem research brief in local memory",
                kind=ActionKind.LOCAL,
                cost_cents=0,
                reason="Turn a broad idea into a falsifiable customer and problem hypothesis.",
                expected_upside="A clearer basis for a useful prototype and later validation.",
                risks="The hypothesis may be wrong because the offline planner has no live web research or customer evidence.",
            ),
            lessons_applied=[
                "No previous evidence is available; avoid spending and validate assumptions first."
            ],
        )


class OpenAIPlanner:
    name = "OpenAI Agents SDK"

    def __init__(self, model: str, max_turns: int):
        self.model = model
        self.max_turns = max_turns

    def decide(
        self, ledger: LedgerSummary, memories: list[dict], research: list[dict]
    ) -> BusinessDecision:
        # Import lazily so ledger/approval commands and tests do not require an API connection.
        from agents import Agent, Runner  # type: ignore[import-not-found]

        agent = Agent(
            name="Safety-first business strategist",
            model=self.model,
            instructions=(
                f"Objective: {OBJECTIVE}\nRules: {SAFETY_RULES}\n"
                "Compare concrete opportunities across demand evidence, startup cost, time to first "
                "revenue, margins, competition, difficulty, skills, automation fit, scalability, "
                "legal/platform constraints, risk, and testability within $100. Apply prior lessons, "
                "choose exactly one strategy, and propose only one next action. Do not claim research "
                "or execution that did not occur. External, financial, communication, publication, "
                "agreement, and account actions will be approval-gated by the application. "
                "Use research record IDs in research_citations. Treat findings marked inferred or "
                "uncertain as assumptions, never verified facts. Explain evidence gaps in assumptions."
            ),
            output_type=BusinessDecision,
        )
        context = {
            "ledger": ledger.__dict__,
            "recent_memory": memories,
            "current_web_research": research,
        }
        result = Runner.run_sync(
            agent,
            "Review this local state and make the best next business decision:\n"
            + json.dumps(context, default=str),
            max_turns=self.max_turns,
        )
        return result.final_output


def build_planner(model: str, max_turns: int) -> Planner:
    if os.getenv("OPENAI_API_KEY"):
        return OpenAIPlanner(model, max_turns)
    return OfflinePlanner()
