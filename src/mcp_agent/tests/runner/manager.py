"""Facade for executing tests via the new multi-language adapters."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Mapping

from mcp_agent.artifacts.index import ArtifactIndex

from .factory import select_runner
from .result import TestRunnerResult
from .spec import TestRunnerConfig, TestRunnerSpec
from .telemetry import TestRunTelemetry


@dataclass(slots=True)
class TestRunnerManager:
    artifact_root: Path | None = None
    telemetry: TestRunTelemetry | None = None
    _artifact_index: ArtifactIndex = field(init=False, repr=False)
    _telemetry: TestRunTelemetry = field(init=False, repr=False)

    __test__ = False

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "_artifact_index",
            ArtifactIndex(self.artifact_root) if self.artifact_root else ArtifactIndex(),
        )
        object.__setattr__(
            self,
            "_telemetry",
            self.telemetry or TestRunTelemetry(),
        )

    def run(self, spec: TestRunnerSpec, config: TestRunnerConfig | None = None) -> TestRunnerResult:
        config = config or TestRunnerConfig(project_root=spec.project_root)
        if config.artifact_root:
            artifact_index = ArtifactIndex(config.artifact_root)
        else:
            artifact_index = self._artifact_index
        runner = select_runner(spec)
        runner.artifact_index = artifact_index
        runner.telemetry = self._telemetry
        return runner.execute(spec, config)


__all__ = ["TestRunnerManager"]
