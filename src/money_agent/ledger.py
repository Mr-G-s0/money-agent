from __future__ import annotations

from dataclasses import dataclass

from money_agent.storage import Database, utc_now


@dataclass(frozen=True)
class LedgerSummary:
    starting_balance_cents: int
    current_cash_cents: int
    expenses_cents: int
    revenue_cents: int
    realized_profit_cents: int
    pending_expenses_cents: int


class Ledger:
    def __init__(self, database: Database):
        self.database = database

    def record(self, *, amount_cents: int, kind: str, status: str, description: str, reason: str) -> int:
        if amount_cents < 0:
            raise ValueError("amount_cents cannot be negative")
        if kind not in {"expense", "revenue"}:
            raise ValueError("kind must be expense or revenue")
        if status not in {"realized", "pending", "cancelled"}:
            raise ValueError("invalid transaction status")
        if kind == "revenue" and status == "pending":
            raise ValueError("projected revenue belongs in memory, never in the ledger")
        if kind == "expense" and status == "realized" and amount_cents > self.summary().current_cash_cents:
            raise ValueError("expense exceeds current cash; debt is forbidden")
        with self.database.connect() as connection:
            cursor = connection.execute(
                "INSERT INTO ledger_transactions(amount_cents, kind, status, description, reason, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (amount_cents, kind, status, description, reason, utc_now()),
            )
            if cursor.lastrowid is None:  # pragma: no cover - SQLite always provides this
                raise RuntimeError("SQLite did not return a transaction ID")
            return cursor.lastrowid

    def summary(self) -> LedgerSummary:
        with self.database.connect() as connection:
            starting = int(connection.execute(
                "SELECT value FROM meta WHERE key='starting_balance_cents'"
            ).fetchone()[0])
            rows = connection.execute(
                "SELECT kind, status, COALESCE(SUM(amount_cents), 0) total "
                "FROM ledger_transactions GROUP BY kind, status"
            ).fetchall()
        totals = {(row["kind"], row["status"]): int(row["total"]) for row in rows}
        revenue = totals.get(("revenue", "realized"), 0)
        expenses = totals.get(("expense", "realized"), 0)
        return LedgerSummary(
            starting_balance_cents=starting,
            current_cash_cents=starting + revenue - expenses,
            expenses_cents=expenses,
            revenue_cents=revenue,
            realized_profit_cents=revenue - expenses,
            pending_expenses_cents=totals.get(("expense", "pending"), 0),
        )
