"""Helper for accounting LLM active time only.

The production controller keeps meticulous accounting of how long the language
model is actively engaged.  This lightweight helper mirrors that behaviour with
simple ``start``/``stop`` semantics.  It can be shared by unit tests and by the
public API which needs to surface budget snapshots alongside every SSE event.
"""

from __future__ import annotations

import time
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Iterator


@dataclass
class BudgetWindow:
    """Represents a timed window."""

    started_at: float
    stopped_at: float | None = None

    @property
    def duration_ms(self) -> int:
        end = self.stopped_at if self.stopped_at is not None else time.time()
        return int((end - self.started_at) * 1000)


class LLMBudget:
    """Simple wall-clock budget that counts LLM active time only."""

    def __init__(self, *, limit_seconds: float | None = None) -> None:
        self._limit_seconds = limit_seconds
        self._windows: list[BudgetWindow] = []
        self._active: BudgetWindow | None = None

    def start(self) -> None:
        if self._active is None:
            self._active = BudgetWindow(time.time())

    def stop(self) -> None:
        if self._active is not None:
            self._active.stopped_at = time.time()
            self._windows.append(self._active)
            self._active = None

    @contextmanager
    def track(self) -> Iterator[None]:
        self.start()
        try:
            yield
        finally:
            self.stop()

    @property
    def active_ms(self) -> int:
        total = sum(window.duration_ms for window in self._windows)
        if self._active is not None:
            total += self._active.duration_ms
        return total

    def remaining_seconds(self) -> float | None:
        if self._limit_seconds is None:
            return None
        return max(self._limit_seconds - self.active_ms / 1000.0, 0.0)

    def exceeded(self) -> bool:
        if self._limit_seconds is None:
            return False
        return self.active_ms / 1000.0 >= self._limit_seconds


__all__ = ["LLMBudget"]
