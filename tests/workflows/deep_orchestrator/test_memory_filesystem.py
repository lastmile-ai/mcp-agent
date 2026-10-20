"""Filesystem persistence contracts for the orchestrator workspace."""

from mcp_agent.workflows.deep_orchestrator.memory import WorkspaceMemory


def test_nested_workspace_creates_its_directories(tmp_path):
    """A configured workspace may have parents that do not exist yet."""
    workspace = tmp_path / "runs" / "research" / "workspace"

    memory = WorkspaceMemory(workspace_dir=workspace)

    assert memory.get_scratchpad_path().is_dir()
    assert (workspace / "artifacts").is_dir()


def test_artifact_is_persisted_as_utf8(tmp_path):
    """Multilingual model output round-trips through the artifact file."""
    memory = WorkspaceMemory(workspace_dir=tmp_path / "workspace")
    content = "研究结果: 日本語 🤖\nRésumé: café"

    memory.save_artifact("report.txt", content, to_filesystem=True)

    assert memory.get_artifact("report.txt") == content
    assert (memory.workspace_dir / "artifacts" / "report.txt").read_text(
        encoding="utf-8"
    ) == content


def test_filesystem_disabled_does_not_create_workspace(tmp_path):
    """In-memory use still works without creating filesystem directories."""
    workspace = tmp_path / "not-created" / "workspace"
    memory = WorkspaceMemory(use_filesystem=False, workspace_dir=workspace)

    memory.save_artifact("report.txt", "🤖", to_filesystem=True)

    assert memory.get_artifact("report.txt") == "🤖"
    assert memory.get_scratchpad_path() is None
    assert not workspace.exists()
