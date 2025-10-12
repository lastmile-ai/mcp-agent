"""Bash test adapter (shunit2, bats, custom scripts)."""

from __future__ import annotations

from pathlib import Path

from ..base import TestRunner
from ..spec import TestRunnerSpec


class BashTestRunner(TestRunner):
    language = "bash"

    def defaults(self, spec: TestRunnerSpec) -> TestRunnerSpec:
        junit_path = spec.junit_path or Path(".mcp-agent/test-results/bash-junit.xml")
        commands = spec.commands
        if not commands:
            commands = [["bash", "run-tests.sh"]]
        return TestRunnerSpec(
            language=self.language,
            commands=commands,
            junit_path=junit_path,
            project_root=spec.project_root,
            timeout=spec.timeout,
            env=spec.env,
            name=spec.name or "bash-tests",
        )


__all__ = ["BashTestRunner"]
