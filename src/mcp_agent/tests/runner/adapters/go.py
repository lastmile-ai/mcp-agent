"""Go test adapter."""

from __future__ import annotations

from pathlib import Path

from ..base import TestRunner
from ..spec import TestRunnerSpec


class GoTestRunner(TestRunner):
    language = "go"

    def defaults(self, spec: TestRunnerSpec) -> TestRunnerSpec:
        junit_path = spec.junit_path or Path(".mcp-agent/test-results/go-junit.xml")
        commands = spec.commands
        if not commands:
            commands = [["go", "test", "./...", "-json"]]
        return TestRunnerSpec(
            language=self.language,
            commands=commands,
            junit_path=junit_path,
            project_root=spec.project_root,
            timeout=spec.timeout,
            env=spec.env,
            name=spec.name or "go-test",
        )


__all__ = ["GoTestRunner"]
