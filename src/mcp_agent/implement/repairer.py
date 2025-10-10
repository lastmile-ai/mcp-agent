"""Simplified repair helper."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from mcp_agent.budget.llm_budget import LLMBudget


@dataclass
class RepairResult:
    diff: str
    attempts: int


class Repairer:
    def __init__(self, budget: LLMBudget | None = None) -> None:
        self._budget = budget or LLMBudget()
        self.attempts = 0

    async def run(self, failing_tests: Iterable[str]) -> RepairResult:
        self.attempts += 1
        with self._budget.track():
            diff = "\n".join(f"# repair for {test}" for test in failing_tests) or "# repair"
        return RepairResult(diff=diff, attempts=self.attempts)


__all__ = ["Repairer", "RepairResult"]
