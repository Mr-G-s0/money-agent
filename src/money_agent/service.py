from __future__ import annotations

import json
from dataclasses import dataclass, replace

from money_agent.approvals import ApprovalRequest, ApprovalService
from money_agent.creation import AssetCreator, CreationReport
from money_agent.ledger import Ledger, LedgerSummary
from money_agent.models import BusinessDecision
from money_agent.planner import Planner
from money_agent.research import ResearchReport, ResearchService, recent_research
from money_agent.safety import requires_approval
from money_agent.storage import Database
from money_agent.workspace import ArtifactStore, Workspace


@dataclass(frozen=True)
class RunReport:
    planner_name: str
    ledger: LedgerSummary
    decision: BusinessDecision
    approval: ApprovalRequest | None
    execution_note: str
    research: ResearchReport | None
    creation: CreationReport | None = None


class BusinessAgent:
    def __init__(
        self,
        database: Database,
        planner: Planner,
        research_service: ResearchService | None = None,
        workspace: Workspace | None = None,
    ):
        self.database = database
        self.planner = planner
        self.ledger = Ledger(database)
        self.approvals = ApprovalService(database, self.ledger)
        self.research_service = research_service
        self.creator = AssetCreator(workspace, ArtifactStore(database)) if workspace else None

    def run_once(self) -> RunReport:
        self.database.initialize()
        ledger = self.ledger.summary()
        memories = self.database.memories()
        research_report = self.research_service.collect() if self.research_service else None
        research = research_report.records if research_report else recent_research(self.database)
        decision = self.planner.decide(ledger, memories, research)
        valid_ids = {item["id"] for item in research}
        valid_citations = [item for item in decision.research_citations if item in valid_ids]
        if len(valid_citations) != len(decision.research_citations):
            decision = replace(
                decision,
                research_citations=valid_citations,
                assumptions=[
                    *decision.assumptions,
                    "One or more unsupported citations were removed.",
                ],
            )

        self.database.remember(
            "decision",
            decision.model_dump_json(),
            {"planner": self.planner.name, "status": "proposed"},
        )

        creation = None
        if self.creator:
            creation = self.creator.create(
                decision.selected_strategy, decision.rationale, valid_citations
            )
            self.database.remember(
                "artifact_evaluation",
                creation.evaluation,
                {"artifact_ids": [item.id for item in creation.artifacts], "status": "evaluated"},
            )
        self.database.remember(
            "strategy", decision.selected_strategy, {"rationale": decision.rationale}
        )

        approval = None
        if requires_approval(decision.next_action):
            approval = self.approvals.request(decision.next_action)
            note = "PROPOSED ONLY: approval required; no action was executed."
        elif decision.next_action.description == (
            "Draft a private one-page customer/problem research brief in local memory"
        ):
            # V2 has no general-purpose executor. It can only record completion of this exact,
            # harmless local planning step; it never represents an external result as executed.
            artifact = {
                "customer_hypothesis": "A narrow customer segment with a repetitive manual task",
                "problem_hypothesis": "Existing generic templates require too much customization",
                "evidence_status": "unvalidated",
                "next_test": "Use saved research to test the customer/problem hypothesis",
            }
            self.database.remember(
                "experiment",
                json.dumps(artifact),
                {
                    "status": "executed_locally",
                    "action": decision.next_action.description,
                },
            )
            note = "EXECUTED LOCALLY: recorded a private, unvalidated research brief; no external action occurred."
        else:
            note = "PROPOSED ONLY: no matching local executor exists; no action was executed."
        return RunReport(
            self.planner.name, ledger, decision, approval, note, research_report, creation
        )
