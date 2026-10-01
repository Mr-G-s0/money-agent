import pytest

from money_agent.approvals import ApprovalService
from money_agent.ledger import Ledger
from money_agent.models import ActionKind, ProposedAction
from money_agent.safety import SafetyViolation, requires_approval
from money_agent.storage import Database


@pytest.fixture
def services(tmp_path):
    database = Database(tmp_path / "agent.db")
    database.initialize()
    ledger = Ledger(database)
    return database, ledger, ApprovalService(database, ledger)


def action(kind=ActionKind.EXTERNAL, cost=0, description="Publish a listing"):
    return ProposedAction(description=description, kind=kind, cost_cents=cost,
                          reason="Validate demand", expected_upside="Potential customers",
                          risks="May receive no interest")


@pytest.mark.parametrize("kind", [
    ActionKind.EXTERNAL, ActionKind.FINANCIAL, ActionKind.COMMUNICATION,
    ActionKind.PUBLICATION, ActionKind.AGREEMENT, ActionKind.ACCOUNT,
])
def test_every_consequential_action_requires_approval(kind):
    assert requires_approval(action(kind=kind))


def test_any_spend_requires_approval():
    assert requires_approval(action(kind=ActionKind.LOCAL, cost=1))


def test_approval_snapshot_contains_required_financial_fields(services):
    _, _, approvals = services
    request = approvals.request(action(cost=2_500))
    assert request.current_cash_cents == 10_000
    assert request.cash_after_action_cents == 7_500
    assert request.cost_cents == 2_500


def test_approval_does_not_execute_or_charge_action(services):
    database, ledger, approvals = services
    request = approvals.request(action(cost=2_500))
    approvals.resolve(request.id, approve=True)
    assert ledger.summary().current_cash_cents == 10_000
    with database.connect() as connection:
        assert connection.execute("SELECT COUNT(*) FROM ledger_transactions").fetchone()[0] == 0


def test_prohibited_action_is_rejected_before_approval(services):
    _, _, approvals = services
    with pytest.raises(SafetyViolation):
        approvals.request(action(description="Send spam messages"))


def test_cannot_propose_debt_financed_action(services):
    _, _, approvals = services
    with pytest.raises(ValueError, match="debt"):
        approvals.request(action(cost=10_001))

