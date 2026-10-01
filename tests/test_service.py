from money_agent.models import ActionKind, BusinessDecision, Opportunity, ProposedAction
from money_agent.service import BusinessAgent
from money_agent.storage import Database


class ApprovalGatedPlanner:
    name = "test planner"

    def decide(self, ledger, memories, research):
        opportunity = Opportunity(
            name="Test strategy",
            summary="Test",
            startup_cost_cents=0,
            expected_return="Unknown",
            difficulty=1,
            time_required="One hour",
            scalability=1,
            competition=1,
            risk=1,
            time_to_first_revenue="Unknown",
            expected_margin="Unknown",
            required_skills=["testing"],
            automation_fit=1,
            legal_platform_constraints="None known",
            testable_within_budget=True,
        )
        return BusinessDecision(
            opportunities=[
                opportunity,
                Opportunity(
                    name="Alternative",
                    summary="Test",
                    startup_cost_cents=0,
                    expected_return="Unknown",
                    difficulty=1,
                    time_required="One hour",
                    scalability=1,
                    competition=1,
                    risk=1,
                    time_to_first_revenue="Unknown",
                    expected_margin="Unknown",
                    required_skills=["testing"],
                    automation_fit=1,
                    legal_platform_constraints="None known",
                    testable_within_budget=True,
                ),
            ],
            selected_strategy="Test strategy",
            rationale="Test the boundary",
            action_plan=["Ask"],
            next_action=ProposedAction(
                description="Email a person",
                kind=ActionKind.COMMUNICATION,
                reason="Ask permission",
                expected_upside="Feedback",
                risks="Unwanted contact",
            ),
            research_citations=[999],
        )


def test_service_proposes_but_does_not_execute_external_action(tmp_path):
    database = Database(tmp_path / "agent.db")
    report = BusinessAgent(database, ApprovalGatedPlanner()).run_once()
    assert report.approval is not None
    assert report.execution_note.startswith("PROPOSED ONLY")
    assert report.decision.research_citations == []
    assert "unsupported citations" in report.decision.assumptions[-1]
    categories = [item["category"] for item in database.memories()]
    assert categories == ["decision", "strategy"]
