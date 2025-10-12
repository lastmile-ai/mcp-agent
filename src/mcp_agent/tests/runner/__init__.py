"""Multi-language test runner abstraction with artifact and telemetry support."""

from .spec import TestRunnerSpec, TestRunnerConfig
from .result import TestRunnerResult, NormalizedTestRun, NormalizedTestSuite, NormalizedTestCase
from .factory import select_runner, detect_project_language
from .manager import TestRunnerManager

__all__ = [
    "TestRunnerSpec",
    "TestRunnerConfig",
    "TestRunnerResult",
    "NormalizedTestRun",
    "NormalizedTestSuite",
    "NormalizedTestCase",
    "select_runner",
    "detect_project_language",
    "TestRunnerManager",
]
