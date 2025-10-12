"""Lightweight telemetry bridge for test runner executions."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Mapping, MutableMapping


@dataclass(slots=True)
class TestRunTelemetry:
    logger_name: str = "mcp_agent.tests.runner"
    _logger: logging.Logger = field(init=False, repr=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "_logger", logging.getLogger(self.logger_name))

    def emit_event(
        self,
        *,
        runner: str,
        result: str,
        duration: float,
        exit_code: int,
        artifacts: Mapping[str, str],
        junit_hash: str,
        extra: Mapping[str, str] | None = None,
    ) -> None:
        payload: MutableMapping[str, object] = {
            "event": "test_run",
            "runner": runner,
            "result": result,
            "duration_seconds": duration,
            "exit_code": exit_code,
            "artifacts": dict(artifacts),
            "junit_hash": junit_hash,
        }
        if extra:
            payload["attributes"] = dict(extra)
        self._logger.info("test_runner_event", extra=payload)


__all__ = ["TestRunTelemetry"]
