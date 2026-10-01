from __future__ import annotations

import argparse
import os
from datetime import timedelta
from decimal import Decimal
from pathlib import Path

from money_agent.config import Settings
from money_agent.planner import OBJECTIVE, build_planner
from money_agent.research import (
    OpenAIWebSearchProvider,
    ResearchLimits,
    ResearchService,
    recent_research,
)
from money_agent.service import BusinessAgent
from money_agent.storage import Database
from money_agent.workspace import Workspace, WorkspaceLimits


def dollars(cents: int) -> str:
    return f"${Decimal(cents) / 100:.2f}"


def load_local_env(path: Path = Path(".env")) -> None:
    """Load simple KEY=VALUE settings without overriding the real environment."""
    if not path.is_file():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip("'\""))


def run() -> int:
    settings = Settings.from_env()
    database = Database(settings.database_path, settings.starting_balance_cents)
    planner = build_planner(settings.model, settings.max_turns)
    research_service = None
    if os.getenv("OPENAI_API_KEY"):
        research_service = ResearchService(
            database,
            OpenAIWebSearchProvider(settings.model),
            ResearchLimits(
                max_queries=settings.research_max_queries,
                max_sources=settings.research_max_sources,
                stale_after=timedelta(hours=settings.research_stale_hours),
            ),
        )
    workspace = Workspace(
        settings.workspace_path,
        WorkspaceLimits(
            max_files=settings.workspace_max_files,
            max_bytes=settings.workspace_max_bytes,
            max_files_per_run=settings.creation_max_files_per_run,
            max_execution_attempts=settings.execution_max_attempts,
            max_operations=settings.workspace_max_operations,
        ),
    )
    report = BusinessAgent(database, planner, research_service, workspace).run_once()
    decision = report.decision

    print("\nMONEY AGENT — VERSION 3 (LOCAL CREATION; SIMULATION ONLY)")
    print(f"Objective: {OBJECTIVE}")
    print(f"Planner: {report.planner_name}")
    print(f"Current cash: {dollars(report.ledger.current_cash_cents)}")
    print(f"Realized profit: {dollars(report.ledger.realized_profit_cents)}")
    if report.research:
        print(
            f"Research: {len(report.research.records)} sources, "
            f"{report.research.api_calls} API calls, {report.research.cache_hits} cache hits"
        )
        for error in report.research.errors:
            print(f"Research warning: {error}")
    else:
        print("Research: offline (no API key); using any previously saved sources")
    print("\nOpportunities considered:")
    for opportunity in decision.opportunities:
        print(
            f"- {opportunity.name}: cost {dollars(opportunity.startup_cost_cents)}, "
            f"difficulty {opportunity.difficulty}/5, scalability {opportunity.scalability}/5, "
            f"competition {opportunity.competition}/5, risk {opportunity.risk}/5, "
            f"automation fit {opportunity.automation_fit}/5"
        )
    print(f"\nSelected strategy: {decision.selected_strategy}")
    print(f"Why: {decision.rationale}")
    if decision.research_citations:
        print("Research citations:")
        cited = {item["id"]: item for item in recent_research(database)}
        for citation_id in decision.research_citations:
            source = cited.get(citation_id)
            if source:
                print(f"  [{citation_id}] {source['source_title']} — {source['source_url']}")
    if decision.assumptions:
        print("Assumptions / uncertainties:")
        for assumption in decision.assumptions:
            print(f"  - {assumption}")
    print("Action plan:")
    for number, step in enumerate(decision.action_plan, 1):
        print(f"  {number}. {step}")
    print(f"\nNext action: {decision.next_action.description}")
    print(report.execution_note)
    if report.creation:
        print("\nCreated and evaluated local artifacts:")
        for artifact in report.creation.artifacts:
            print(f"  [{artifact.id}] {artifact.file_path} — {artifact.status}")
        print(f"Evaluation: {report.creation.evaluation}")
    if report.approval:
        item = report.approval
        print("\nAPPROVAL REQUEST")
        print(f"ACTION: {item.action}\nCOST: {dollars(item.cost_cents)}\nREASON: {item.reason}")
        print(f"EXPECTED UPSIDE: {item.expected_upside}\nRISKS: {item.risks}")
        print(f"CURRENT CASH: {dollars(item.current_cash_cents)}")
        print(f"CASH AFTER ACTION: {dollars(item.cash_after_action_cents)}")
        print(f"Approval ID: {item.id} (recorded only; V3 will not execute external actions)")
    print(f"\nState saved to: {settings.database_path}")
    return 0


def main() -> int:
    load_local_env()
    parser = argparse.ArgumentParser(description="Run the simulated money agent")
    parser.parse_args()
    return run()


if __name__ == "__main__":
    raise SystemExit(main())
