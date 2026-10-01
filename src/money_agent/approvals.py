from __future__ import annotations

from dataclasses import dataclass

from money_agent.ledger import Ledger
from money_agent.models import ProposedAction
from money_agent.safety import requires_approval
from money_agent.storage import Database, utc_now


@dataclass(frozen=True)
class ApprovalRequest:
    id: int
    action: str
    cost_cents: int
    reason: str
    expected_upside: str
    risks: str
    current_cash_cents: int
    cash_after_action_cents: int


class ApprovalService:
    def __init__(self, database: Database, ledger: Ledger):
        self.database = database
        self.ledger = ledger

    def request(self, action: ProposedAction) -> ApprovalRequest:
        if not requires_approval(action):
            raise ValueError("local zero-cost action does not need approval")
        cash = self.ledger.summary().current_cash_cents
        if action.cost_cents > cash:
            raise ValueError("action exceeds available cash; debt is forbidden")
        with self.database.connect() as connection:
            cursor = connection.execute(
                "INSERT INTO approvals(action, action_kind, cost_cents, reason, expected_upside, "
                "risks, cash_before_cents, cash_after_cents, status, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?)",
                (action.description, action.kind.value, action.cost_cents, action.reason,
                 action.expected_upside, action.risks, cash, cash - action.cost_cents, utc_now()),
            )
            if cursor.lastrowid is None:  # pragma: no cover - SQLite always provides this
                raise RuntimeError("SQLite did not return an approval ID")
            approval_id = cursor.lastrowid
        return ApprovalRequest(approval_id, action.description, action.cost_cents, action.reason,
                               action.expected_upside, action.risks, cash, cash - action.cost_cents)

    def resolve(self, approval_id: int, approve: bool) -> None:
        status = "approved" if approve else "rejected"
        with self.database.connect() as connection:
            row = connection.execute(
                "SELECT status FROM approvals WHERE id=?", (approval_id,)
            ).fetchone()
            if row is None:
                raise KeyError(f"approval {approval_id} not found")
            if row["status"] != "pending":
                raise ValueError("approval was already resolved")
            connection.execute(
                "UPDATE approvals SET status=?, resolved_at=? WHERE id=?",
                (status, utc_now(), approval_id),
            )
