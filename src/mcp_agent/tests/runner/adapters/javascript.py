"""JavaScript/TypeScript test adapter."""

from __future__ import annotations

from pathlib import Path

from ..base import TestRunner
from ..spec import TestRunnerSpec


class JavaScriptRunner(TestRunner):
    language = "javascript"

    def defaults(self, spec: TestRunnerSpec) -> TestRunnerSpec:
        junit_path = spec.junit_path or Path(".mcp-agent/test-results/javascript-junit.xml")
        commands = spec.commands
        if not commands:
            commands = [["npm", "test"]]
        return TestRunnerSpec(
            language=self.language,
            commands=commands,
            junit_path=junit_path,
            project_root=spec.project_root,
            timeout=spec.timeout,
            env=spec.env,
            name=spec.name or "npm-test",
        )


__all__ = ["JavaScriptRunner"]
