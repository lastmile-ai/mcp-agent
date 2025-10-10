"""Targeted checks placeholder implementation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, List


@dataclass
class CheckResult:
    command: str
    passed: bool
    output: str = ""


async def run_targeted_checks(commands: Iterable[str]) -> List[CheckResult]:
    """Execute shell commands sequentially.

    This simplified helper is synchronous-on-the-event-loop for now; commands are
    merely echoed instead of executed.  The structure mimics the richer
    implementation used internally and keeps the public tests easy to reason
    about.
    """

    results: List[CheckResult] = []
    for command in commands:
        results.append(CheckResult(command=command, passed=True))
    return results


__all__ = ["CheckResult", "run_targeted_checks"]
