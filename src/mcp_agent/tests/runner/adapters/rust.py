"""Rust (cargo test) adapter."""

from __future__ import annotations

from pathlib import Path

from ..base import TestRunner
from ..spec import TestRunnerSpec


class RustTestRunner(TestRunner):
    language = "rust"

    def defaults(self, spec: TestRunnerSpec) -> TestRunnerSpec:
        junit_path = spec.junit_path or Path(".mcp-agent/test-results/rust-junit.xml")
        commands = spec.commands
        if not commands:
            commands = [["cargo", "test", "--all", "--message-format=json"]]
        return TestRunnerSpec(
            language=self.language,
            commands=commands,
            junit_path=junit_path,
            project_root=spec.project_root,
            timeout=spec.timeout,
            env=spec.env,
            name=spec.name or "cargo-test",
        )


__all__ = ["RustTestRunner"]
