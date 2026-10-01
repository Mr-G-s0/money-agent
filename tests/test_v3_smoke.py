from money_agent.ledger import Ledger
from money_agent.planner import OfflinePlanner
from money_agent.service import BusinessAgent
from money_agent.storage import Database
from money_agent.workspace import ArtifactStore, Workspace, WorkspaceLimits


def test_offline_v3_run_creates_evaluates_and_stays_local(tmp_path):
    database = Database(tmp_path / "agent.db")
    workspace = Workspace(tmp_path / "workspace", WorkspaceLimits())
    report = BusinessAgent(database, OfflinePlanner(), workspace=workspace).run_once()

    assert report.ledger.current_cash_cents == 10_000
    assert report.creation is not None
    assert report.creation.artifacts[0].status == "verified"
    assert workspace.read_text(report.creation.artifacts[0].file_path).startswith("# Niche")
    assert ArtifactStore(database).for_opportunity(report.decision.selected_strategy)
    assert Ledger(database).summary().current_cash_cents == 10_000
    assert report.approval is None
    with database.connect() as connection:
        assert connection.execute("SELECT COUNT(*) FROM approvals").fetchone()[0] == 0
        assert connection.execute("SELECT COUNT(*) FROM ledger_transactions").fetchone()[0] == 0
