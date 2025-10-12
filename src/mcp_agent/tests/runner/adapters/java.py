"""Java (JUnit/Maven/Gradle) adapter."""

from __future__ import annotations

from pathlib import Path

from ..base import TestRunner
from ..spec import TestRunnerSpec


class JavaRunner(TestRunner):
    language = "java"

    def defaults(self, spec: TestRunnerSpec) -> TestRunnerSpec:
        junit_path = spec.junit_path or Path(".mcp-agent/test-results/java-junit.xml")
        commands = spec.commands
        if not commands:
            if (spec.project_root or Path.cwd()).joinpath("gradlew").exists():
                commands = [["./gradlew", "test"]]
            else:
                commands = [["mvn", "test"]]
        return TestRunnerSpec(
            language=self.language,
            commands=commands,
            junit_path=junit_path,
            project_root=spec.project_root,
            timeout=spec.timeout,
            env=spec.env,
            name=spec.name or "junit",
        )


__all__ = ["JavaRunner"]
