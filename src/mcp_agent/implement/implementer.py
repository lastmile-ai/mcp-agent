"""Minimal stand-in for the patch implementer."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from mcp_agent.budget.llm_budget import LLMBudget


@dataclass
class ImplementerResult:
    diff: str
    files: list[str]


class Implementer:
    def __init__(self, budget: LLMBudget | None = None) -> None:
        self._budget = budget or LLMBudget()

    async def run(self, instructions: str, files: Iterable[str]) -> ImplementerResult:
        with self._budget.track():
            # The simplified version just echoes a comment header for each file.
            diff_lines = [f"# change requested: {instructions.strip()}"]
            affected = list(files)
        return ImplementerResult(diff="\n".join(diff_lines), files=affected)


__all__ = ["Implementer", "ImplementerResult"]
