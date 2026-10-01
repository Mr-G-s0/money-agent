import json

import pytest

from money_agent.creation import AssetCreator
from money_agent.storage import Database
from money_agent.workspace import (
    ArtifactStore,
    ExecutionKind,
    Workspace,
    WorkspaceLimits,
    WorkspaceViolation,
)


def make_workspace(tmp_path, **overrides):
    values = dict(max_files=10, max_bytes=10_000, max_files_per_run=5, max_execution_attempts=2)
    values.update(overrides)
    return Workspace(tmp_path / "workspace", WorkspaceLimits(**values))


@pytest.mark.parametrize("path", ["../escape.txt", "/tmp/escape.txt", "nested/../../escape"])
def test_path_traversal_and_absolute_paths_are_blocked(tmp_path, path):
    workspace = make_workspace(tmp_path)
    with pytest.raises(WorkspaceViolation):
        workspace.write_text(path, "no")


@pytest.mark.parametrize(
    "path",
    [".env", ".env.local", ".ssh/id_rsa", "credentials.json", "keys/secret.pem", "api_token.txt"],
)
def test_sensitive_file_access_is_blocked(tmp_path, path):
    workspace = make_workspace(tmp_path)
    with pytest.raises(WorkspaceViolation):
        workspace.read_text(path)


def test_system_or_user_root_cannot_be_the_workspace():
    with pytest.raises(WorkspaceViolation):
        Workspace("/", WorkspaceLimits())


def test_create_modify_and_structured_files(tmp_path):
    workspace = make_workspace(tmp_path)
    workspace.write_text("project/readme.md", "first")
    assert workspace.read_text("project/readme.md") == "first"
    workspace.write_text("project/readme.md", "second", overwrite=True)
    workspace.write_json("project/data.json", {"safe": True})
    workspace.write_csv("project/table.csv", [["name", "value"], ["a", "1"]])
    assert workspace.read_text("project/readme.md") == "second"
    assert json.loads(workspace.read_text("project/data.json")) == {"safe": True}
    assert "name,value" in workspace.read_text("project/table.csv")


def test_file_count_and_workspace_size_limits(tmp_path):
    limited = make_workspace(tmp_path, max_files=1, max_files_per_run=1, max_bytes=4)
    limited.write_text("one.txt", "1234")
    with pytest.raises(WorkspaceViolation, match="file-count"):
        limited.write_text("two.txt", "x")
    with pytest.raises(WorkspaceViolation, match="workspace-size"):
        limited.write_text("one.txt", "12345", overwrite=True)


def test_workspace_operation_limit(tmp_path):
    workspace = make_workspace(tmp_path, max_operations=1)
    workspace.write_text("one.txt", "one")
    with pytest.raises(WorkspaceViolation, match="operation"):
        workspace.read_text("one.txt")


def test_symlink_escape_is_blocked(tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    workspace = make_workspace(tmp_path)
    (workspace.root / "link").symlink_to(outside, target_is_directory=True)
    with pytest.raises(WorkspaceViolation):
        workspace.write_text("link/file.txt", "no")


def test_safe_execution_compile_and_restrictions(tmp_path):
    workspace = make_workspace(tmp_path)
    workspace.write_text("safe.py", "print(sum(range(4)))\n")
    assert workspace.execute("safe.py", ExecutionKind.PYTHON_COMPILE).success
    assert workspace.execute("safe.py", ExecutionKind.RESTRICTED_PYTHON).output.strip() == "6"

    other = make_workspace(tmp_path / "other")
    other.write_text("unsafe.py", "import os\nos.system('echo no')\n")
    with pytest.raises(WorkspaceViolation, match="Import"):
        other.execute("unsafe.py", ExecutionKind.RESTRICTED_PYTHON)


def test_artifact_persistence_and_reuse(tmp_path):
    database = Database(tmp_path / "agent.db")
    database.initialize()
    workspace = make_workspace(tmp_path)
    creator = AssetCreator(workspace, ArtifactStore(database))
    first = creator.create("Template pack", "Make work repeatable.", [2])
    second = creator.create("Template pack", "Make work repeatable.", [2, 3])
    assert first.artifacts[0].id == second.artifacts[0].id
    assert second.reused_existing is True
    assert "Improvement revision" in workspace.read_text(first.artifacts[0].file_path)
    saved = ArtifactStore(database).for_opportunity("Template pack")
    assert len(saved) == 1
    assert saved[0].status == "verified"
    assert saved[0].related_research_ids == [2, 3]


@pytest.mark.parametrize(
    ("opportunity", "names"),
    [
        ("Tiny SaaS app", {"index.html", "style.css", "app.js"}),
        ("Spreadsheet consulting service", {"offer.md", "workflow.md", "pricing.csv"}),
    ],
)
def test_creator_selects_strategy_appropriate_asset_family(tmp_path, opportunity, names):
    database = Database(tmp_path / f"{opportunity[:4]}.db")
    database.initialize()
    workspace = make_workspace(tmp_path / opportunity[:4])
    report = AssetCreator(workspace, ArtifactStore(database)).create(opportunity, "Test it.", [])
    assert {artifact.file_path.rsplit("/", 1)[-1] for artifact in report.artifacts} == names
    assert all(artifact.status == "verified" for artifact in report.artifacts)
