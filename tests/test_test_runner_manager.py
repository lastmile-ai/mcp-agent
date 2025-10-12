from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

from mcp_agent.tests.runner import (
    TestRunnerManager,
    TestRunnerSpec,
    TestRunnerConfig,
    detect_project_language,
    select_runner,
)
from mcp_agent.tests.runner.adapters import (
    BashTestRunner,
    GoTestRunner,
    JavaRunner,
    JavaScriptRunner,
    PyTestRunner,
    RustTestRunner,
)


FIXTURES = Path(__file__).parent / "fixtures"
FAKE_TOOL = FIXTURES / "fake_test_tool.py"


@pytest.mark.parametrize(
    "folder,expected",
    [
        ("python_project", "python"),
        ("javascript_project", "javascript"),
        ("java_project", "java"),
        ("go_project", "go"),
        ("rust_project", "rust"),
        ("bash_project", "bash"),
    ],
)
def test_detect_project_language(folder: str, expected: str) -> None:
    root = FIXTURES / folder
    assert detect_project_language(root) == expected


def test_select_runner_by_language() -> None:
    spec = TestRunnerSpec(language="python")
    runner = select_runner(spec)
    assert isinstance(runner, PyTestRunner)

    spec_js = TestRunnerSpec(language="javascript")
    assert isinstance(select_runner(spec_js), JavaScriptRunner)

    spec_java = TestRunnerSpec(language="java")
    assert isinstance(select_runner(spec_java), JavaRunner)

    spec_go = TestRunnerSpec(language="go")
    assert isinstance(select_runner(spec_go), GoTestRunner)

    spec_bash = TestRunnerSpec(language="bash")
    assert isinstance(select_runner(spec_bash), BashTestRunner)

    spec_rust = TestRunnerSpec(language="rust")
    assert isinstance(select_runner(spec_rust), RustTestRunner)


def test_python_runner_executes_and_persists_artifacts(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ARTIFACTS_ROOT", str(tmp_path / "artifacts"))
    project = FIXTURES / "python_project"
    manager = TestRunnerManager(artifact_root=tmp_path / "artifacts")
    spec = TestRunnerSpec(language="python", project_root=project)
    result = manager.run(spec)
    assert result.succeeded
    summary = result.normalized.summary
    assert summary["tests"] >= 1
    artifacts = result.artifacts
    assert {"stdout", "stderr", "junit", "meta"}.issubset(artifacts)
    artifact_root = Path(os.getenv("ARTIFACTS_ROOT"))
    run_dir = artifact_root / result.run_id
    assert run_dir.exists()
    for rel_name in artifacts.values():
        assert (run_dir / rel_name).exists()


@pytest.mark.parametrize("language", ["javascript", "java", "go", "bash", "rust"])
def test_runner_handles_fake_projects(language: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ARTIFACTS_ROOT", str(tmp_path / "artifacts"))
    project = FIXTURES / f"{language}_project"
    junit_name = Path("fake-junit.xml")
    command = [
        sys.executable,
        str(FAKE_TOOL),
        "--language",
        language,
        "--junit",
        junit_name.as_posix(),
    ]
    if language in {"go", "bash"}:
        # exercise synthetic fallback by removing junit flag
        command = [sys.executable, str(FAKE_TOOL), "--language", language]
        junit_path = None
    else:
        junit_path = junit_name
    manager = TestRunnerManager(artifact_root=tmp_path / "artifacts")
    spec = TestRunnerSpec(
        language=language,
        project_root=project,
        commands=[command],
        junit_path=junit_path,
    )
    result = manager.run(spec)
    assert result.language == language
    assert result.exit_code == 0
    assert result.succeeded
    assert result.artifacts["stdout"].endswith("test-stdout.log")
    summary = result.normalized.summary
    assert summary["tests"] >= 1
    if language in {"go", "bash"}:
        assert summary["failures"] == 0
    assert Path(tmp_path / "artifacts").exists()


def test_manager_allows_override_config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ARTIFACTS_ROOT", str(tmp_path / "artifacts"))
    manager = TestRunnerManager(artifact_root=tmp_path / "artifacts")
    spec = TestRunnerSpec(
        language="javascript",
        project_root=FIXTURES / "javascript_project",
        commands=[[sys.executable, str(FAKE_TOOL), "--language", "javascript"]],
    )
    config = TestRunnerConfig(run_id="custom-run", artifact_root=tmp_path / "custom_artifacts")
    result = manager.run(spec, config=config)
    meta_path = Path(config.artifact_root) / config.run_id / result.artifacts["meta"]
    data = json.loads(meta_path.read_text(encoding="utf-8"))
    assert data["language"] == "javascript"
    assert Path(config.artifact_root).exists()
