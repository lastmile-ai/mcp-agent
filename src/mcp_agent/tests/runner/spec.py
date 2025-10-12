"""Runtime configuration objects for the test runner adapters."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Mapping, MutableMapping


@dataclass(slots=True)
class TestRunnerConfig:
    """High level configuration shared across all language adapters."""

    run_id: str | None = None
    project_root: Path | None = None
    artifact_root: Path | None = None
    telemetry_attributes: Mapping[str, str] | None = None

    __test__ = False


@dataclass(slots=True)
class TestRunnerSpec:
    """Specification of a single logical test execution."""

    language: str | None = None
    commands: List[Iterable[str]] | None = None
    env: MutableMapping[str, str] | None = None
    junit_path: Path | None = None
    timeout: float | None = None
    project_root: Path | None = None
    name: str | None = None

    __test__ = False

    def merge(self, other: "TestRunnerSpec") -> "TestRunnerSpec":
        """Combine two specs, preferring non-empty values from ``self``."""

        merged_env: Dict[str, str] | None = None
        if other.env or self.env:
            merged_env = {}
            if other.env:
                merged_env.update(other.env)
            if self.env:
                merged_env.update(self.env)
        return TestRunnerSpec(
            language=self.language or other.language,
            commands=self.commands or other.commands,
            env=merged_env,
            junit_path=self.junit_path or other.junit_path,
            timeout=self.timeout or other.timeout,
            project_root=self.project_root or other.project_root,
            name=self.name or other.name,
        )

    def resolved_commands(self) -> List[List[str]] | None:
        if self.commands is None:
            return None
        return [list(cmd) for cmd in self.commands]


__all__ = ["TestRunnerConfig", "TestRunnerSpec"]

