"""Typed result objects produced by test runner adapters."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Mapping


@dataclass(slots=True)
class NormalizedTestCase:
    name: str
    classname: str | None = None
    status: str = "passed"
    message: str | None = None
    duration: float | None = None


@dataclass(slots=True)
class NormalizedTestSuite:
    name: str
    tests: int
    failures: int
    errors: int
    skipped: int
    time: float | None = None
    cases: List[NormalizedTestCase] = field(default_factory=list)


@dataclass(slots=True)
class NormalizedTestRun:
    suites: List[NormalizedTestSuite] = field(default_factory=list)

    @property
    def summary(self) -> Dict[str, int]:
        total = sum(s.tests for s in self.suites)
        failures = sum(s.failures for s in self.suites)
        errors = sum(s.errors for s in self.suites)
        skipped = sum(s.skipped for s in self.suites)
        return {
            "tests": total,
            "failures": failures,
            "errors": errors,
            "skipped": skipped,
        }


@dataclass(slots=True)
class TestRunnerResult:
    language: str
    run_id: str
    exit_code: int
    duration: float
    stdout: str
    stderr: str
    junit_xml: str
    normalized: NormalizedTestRun
    artifacts: Mapping[str, str]
    command: List[str]

    @property
    def succeeded(self) -> bool:
        return self.exit_code == 0 and self.normalized.summary["failures"] == 0 and self.normalized.summary["errors"] == 0


__all__ = [
    "NormalizedTestCase",
    "NormalizedTestSuite",
    "NormalizedTestRun",
    "TestRunnerResult",
]
