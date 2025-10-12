"""Python specific test adapter."""

from __future__ import annotations

from pathlib import Path

from ..base import TestRunner
from ..spec import TestRunnerSpec


class PyTestRunner(TestRunner):
    language = "python"

    def defaults(self, spec: TestRunnerSpec) -> TestRunnerSpec:
        junit_path = spec.junit_path or Path(".mcp-agent/test-results/python-junit.xml")
        commands = spec.commands
        if not commands:
            commands = [[
                "pytest",
                "-q",
                "--disable-warnings",
                "--junit-xml",
                str(junit_path),
            ]]
        return TestRunnerSpec(
            language=self.language,
            commands=commands,
            junit_path=junit_path,
            project_root=spec.project_root,
            timeout=spec.timeout,
            env=spec.env,
            name=spec.name or "pytest",
        )


__all__ = ["PyTestRunner"]
