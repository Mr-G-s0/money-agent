import json
from pathlib import Path

import pytest

from money_agent.approvals import ApprovalService
from money_agent.creation import AssetCreator
from money_agent.ledger import Ledger
from money_agent.models import ActionKind, ProposedAction
from money_agent.safety import requires_approval
from money_agent.storage import Database
from money_agent.workspace import (
    ArtifactStore,
    ExecutionKind,
    Workspace,
    WorkspaceLimits,
    WorkspaceViolation,
)


def sandbox(tmp_path, **changes):
    settings = {
        "max_files": 20,
        "max_bytes": 200_000,
        "max_files_per_run": 10,
        "max_execution_attempts": 3,
        "max_operations": 50,
        "max_path_depth": 8,
        "max_path_length": 160,
    }
    settings.update(changes)
    return Workspace(tmp_path / "workspace", WorkspaceLimits(**settings))


@pytest.mark.parametrize(
    "attack",
    [
        "../escape",
        "../../escape",
        "valid/../../../escape",
        "valid\\..\\escape",
        "..%2fescape",
        "%2e%2e/escape",
        "%252e%252e%252fescape",
        "valid/∕/escape",
        "valid/／/escape",
        "valid/⧵/escape",
        "．．/escape",
        "．env",
        "valid/./escape",
    ],
)
def test_traversal_encoding_and_odd_separator_attacks_are_rejected(tmp_path, attack):
    with pytest.raises(WorkspaceViolation):
        sandbox(tmp_path).write_text(attack, "escaped")


@pytest.mark.parametrize(
    "attack",
    [
        "/etc/passwd",
        "~/credentials",
        "C:\\",
        "C:\\Users\\victim",
        "C:\\Windows\\system.ini",
        "\\\\server\\share\\file",
        "\\?\\C:\\Windows\\file",
    ],
)
def test_unix_windows_home_and_unc_absolute_paths_are_rejected(tmp_path, attack):
    with pytest.raises(WorkspaceViolation):
        sandbox(tmp_path).read_text(attack)


@pytest.mark.parametrize(
    "attack",
    [
        ".ENV",
        ".env.production.bak",
        "ID_RSA",
        "id_ed25519.pub",
        "credentials.old.json",
        "my-secrets.txt",
        "access_TOKEN.txt",
        "API-KEY.txt",
        ".SSH/config",
        ".aws/credentials",
        ".git-credentials.bak",
        "browser/Profile/LOGIN DATA",
        "cookies.sqlite",
        "private.PEM.txt",
        "secret.key.backup",
        "passwd",
        "shadow",
        " safe.txt",
        "safe.txt ",
    ],
)
def test_sensitive_and_disguised_filenames_are_rejected(tmp_path, attack):
    with pytest.raises(WorkspaceViolation):
        sandbox(tmp_path).write_text(attack, "sensitive")


def test_symlink_file_and_directory_cannot_be_read_or_written(tmp_path):
    workspace = sandbox(tmp_path)
    outside = tmp_path / "outside"
    outside.mkdir()
    secret = outside / "secret.txt"
    secret.write_text("host secret")
    (workspace.root / "directory-link").symlink_to(outside, target_is_directory=True)
    (workspace.root / "file-link").symlink_to(secret)

    for attack in ("directory-link/secret.txt", "file-link"):
        with pytest.raises(WorkspaceViolation):
            workspace.read_text(attack)
        with pytest.raises(WorkspaceViolation):
            workspace.write_text(attack, "changed", overwrite=True)
    assert secret.read_text() == "host secret"


def test_replaced_parent_directory_is_revalidated(tmp_path, monkeypatch):
    workspace = sandbox(tmp_path)
    workspace.write_text("project/original.txt", "safe")
    outside = tmp_path / "outside"
    outside.mkdir()
    original_usage = workspace._usage

    def replace_after_initial_path_validation():
        usage = original_usage()
        (workspace.root / "project").rename(workspace.root / "old-project")
        (workspace.root / "project").symlink_to(outside, target_is_directory=True)
        return usage

    monkeypatch.setattr(workspace, "_usage", replace_after_initial_path_validation)

    with pytest.raises(WorkspaceViolation):
        workspace.write_text("project/escaped.txt", "no")
    assert not (outside / "escaped.txt").exists()


PYTHON_ESCAPE_PAYLOADS = [
    "import os",
    "from pathlib import Path",
    "__import__('os')",
    "print((1).__class__)",
    "getattr(1, 'real')",
    "setattr(1, 'x', 1)",
    "globals()",
    "locals()",
    "vars()",
    "eval('1')",
    "exec('print(1)')",
    "compile('1', 'x', 'exec')",
    "open('/etc/passwd')",
    "lambda: 1",
    "[x for x in range(3)]",
    "try:\n  1/0\nexcept Exception as error:\n  print(error)",
    "def escape():\n  return 1",
    "class Escape:\n  pass",
    "while True:\n  pass",
    "print(10 ** 1000000)",
    "print(range(1000001))",
    "print(__builtins__)",
    "os.system('id')",
    "socket.socket()",
    "requests.get('https://example.com')",
    "subprocess.run(['id'])",
]


@pytest.mark.parametrize("payload", PYTHON_ESCAPE_PAYLOADS)
def test_restricted_python_rejects_escape_payloads(tmp_path, payload):
    workspace = sandbox(tmp_path)
    workspace.write_text("attack.py", payload)
    with pytest.raises(WorkspaceViolation):
        workspace.execute("attack.py", ExecutionKind.RESTRICTED_PYTHON)


def test_execution_output_and_attempts_are_bounded(tmp_path):
    workspace = sandbox(tmp_path, max_execution_attempts=2)
    workspace.write_text("flood.py", "for x in range(10000):\n print('x' * 1000)\n")
    first = workspace.execute("flood.py", ExecutionKind.RESTRICTED_PYTHON)
    assert len(first.output) <= 4020
    workspace.execute("flood.py", ExecutionKind.PYTHON_COMPILE)
    with pytest.raises(WorkspaceViolation, match="execution-attempt"):
        workspace.execute("flood.py", ExecutionKind.PYTHON_COMPILE)


def test_cpu_and_memory_exhaustion_are_contained(tmp_path):
    workspace = sandbox(tmp_path)
    workspace.write_text(
        "cpu.py",
        "total=0\nfor x in range(10000):\n for y in range(10000):\n  total=total+x*y\n",
    )
    cpu = workspace.execute("cpu.py", ExecutionKind.RESTRICTED_PYTHON)
    assert not cpu.success

    workspace.write_text("memory.py", "values=[0]*1000000\nvalues=values*100\nprint(len(values))\n")
    memory = workspace.execute("memory.py", ExecutionKind.RESTRICTED_PYTHON)
    assert not memory.success


def test_deep_paths_large_files_and_revision_floods_stop_cleanly(tmp_path):
    workspace = sandbox(tmp_path, max_files=2, max_files_per_run=2, max_bytes=20, max_path_depth=3)
    with pytest.raises(WorkspaceViolation, match="path-depth"):
        workspace.write_text("a/b/c/d.txt", "x")
    with pytest.raises(WorkspaceViolation, match="workspace-size"):
        workspace.write_text("large.txt", "x" * 21)
    workspace.write_text("one.txt", "1")
    workspace.write_text("two.txt", "2")
    with pytest.raises(WorkspaceViolation, match="file-count"):
        workspace.write_text("three.txt", "3")
    for revision in range(5):
        workspace.write_text("one.txt", str(revision), overwrite=True)
    assert workspace.read_text("one.txt") == "4"


@pytest.mark.parametrize(
    "description",
    [
        "Publish the landing page",
        "Send the drafted email",
        "Upload the files",
        "Deploy the application",
        "Purchase a domain",
        "Create an external account",
        "Change the account password",
        "Contact a prospective customer",
        "Submit a form",
        "Make an HTTP request",
        "Pay the hosting invoice",
    ],
)
def test_external_intent_cannot_hide_behind_local_action_kind(description):
    action = ProposedAction(
        description=description,
        kind=ActionKind.LOCAL,
        reason="Misclassified by an untrusted planner",
        expected_upside="Unknown",
        risks="External effect",
    )
    assert requires_approval(action)


def test_drafting_external_material_locally_remains_allowed():
    action = ProposedAction(
        description="Draft private email copy locally",
        kind=ActionKind.LOCAL,
        reason="Prepare a private draft",
        expected_upside="A reviewable artifact",
        risks="Unvalidated copy",
    )
    assert not requires_approval(action)


def test_approval_and_creation_never_change_ledger(tmp_path):
    database = Database(tmp_path / "agent.db")
    database.initialize()
    ledger = Ledger(database)
    workspace = sandbox(tmp_path)
    AssetCreator(workspace, ArtifactStore(database)).create("Template", "Draft", [])
    action = ProposedAction(
        description="Deploy the artifact",
        kind=ActionKind.LOCAL,
        cost_cents=9_999,
        reason="Test boundary",
        expected_upside="Projected revenue only",
        risks="Could fail",
    )
    approval = ApprovalService(database, ledger).request(action)
    assert approval.cash_after_action_cents == 1
    assert ledger.summary().current_cash_cents == 10_000
    with pytest.raises(ValueError, match="projected revenue"):
        ledger.record(
            amount_cents=1_000,
            kind="revenue",
            status="pending",
            description="Fabricated projection",
            reason="Not realized",
        )
    with pytest.raises(ValueError, match="debt"):
        ledger.record(
            amount_cents=10_001,
            kind="expense",
            status="realized",
            description="Overspend",
            reason="Attack",
        )
    assert ledger.summary().realized_profit_cents == 0


def test_tampered_artifact_path_is_not_reused_after_restart(tmp_path):
    database = Database(tmp_path / "agent.db")
    database.initialize()
    now = "2026-01-01T00:00:00+00:00"
    with database.connect() as connection:
        connection.execute(
            "INSERT INTO artifacts(file_path, artifact_type, purpose, opportunity, created_at, "
            "modified_at, status, evaluation_notes, related_research_ids) VALUES(?,?,?,?,?,?,?,?,?)",
            ("../../escaped.md", "malicious", "escape", "Template", now, now, "draft", "", "[]"),
        )
    database.remember("hostile", "__import__('os').system('id')", {"path": "../../escape"})

    workspace = sandbox(tmp_path)
    report = AssetCreator(workspace, ArtifactStore(database)).create("Template", "Safe", [])
    assert report.artifacts[0].file_path == "projects/template/product.md"
    assert not (tmp_path.parent / "escaped.md").exists()
    assert json.loads(database.memories()[-1]["metadata_json"])["path"] == "../../escape"
    assert Path(workspace.root / report.artifacts[0].file_path).is_file()


def test_malformed_artifact_metadata_is_inert_and_new_bad_paths_are_rejected(tmp_path):
    database = Database(tmp_path / "agent.db")
    database.initialize()
    now = "2026-01-01T00:00:00+00:00"
    with database.connect() as connection:
        connection.execute(
            "INSERT INTO artifacts(file_path, artifact_type, purpose, opportunity, created_at, "
            "modified_at, status, evaluation_notes, related_research_ids) VALUES(?,?,?,?,?,?,?,?,?)",
            ("legacy.md", "text", "test", "Legacy", now, now, "draft", "", "not-json"),
        )
    store = ArtifactStore(database)
    assert store.for_opportunity("Legacy")[0].related_research_ids == []
    with pytest.raises(WorkspaceViolation):
        store.upsert(
            file_path="../../escape.py",
            artifact_type="python",
            purpose="escape",
            opportunity="Attack",
            status="draft",
            evaluation_notes="",
            related_research_ids=[],
        )
