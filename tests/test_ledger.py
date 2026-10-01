import pytest

from money_agent.ledger import Ledger
from money_agent.storage import Database


@pytest.fixture
def ledger(tmp_path):
    database = Database(tmp_path / "agent.db")
    database.initialize()
    return Ledger(database)


def test_new_ledger_starts_with_simulated_100_dollars(ledger):
    summary = ledger.summary()
    assert summary.starting_balance_cents == 10_000
    assert summary.current_cash_cents == 10_000
    assert summary.realized_profit_cents == 0


def test_only_realized_transactions_change_cash_and_profit(ledger):
    ledger.record(amount_cents=2_500, kind="revenue", status="realized",
                  description="Simulated sale", reason="Test")
    ledger.record(amount_cents=700, kind="expense", status="pending",
                  description="Proposed tool", reason="Test")
    ledger.record(amount_cents=400, kind="expense", status="realized",
                  description="Simulated expense", reason="Test")
    summary = ledger.summary()
    assert summary.current_cash_cents == 12_100
    assert summary.realized_profit_cents == 2_100
    assert summary.pending_expenses_cents == 700


def test_projected_revenue_cannot_enter_ledger(ledger):
    with pytest.raises(ValueError, match="projected revenue"):
        ledger.record(amount_cents=99_999, kind="revenue", status="pending",
                      description="Projection", reason="Not earned")


def test_debt_is_forbidden(ledger):
    with pytest.raises(ValueError, match="debt"):
        ledger.record(amount_cents=10_001, kind="expense", status="realized",
                      description="Overspend", reason="Test")

