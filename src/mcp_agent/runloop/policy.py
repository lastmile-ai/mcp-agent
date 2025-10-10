"""Simplified sizing policy for controller iterations."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class PatchSizing:
    iterations: int
    implementation_budget_s: float


def compute_patch_sizing(budget_seconds: float) -> PatchSizing:
    """Return a coarse iteration count based on the overall budget."""

    if budget_seconds <= 0:
        return PatchSizing(iterations=1, implementation_budget_s=0)
    iterations = max(4, min(7, round(budget_seconds / 120)))
    impl_budget = budget_seconds / iterations
    return PatchSizing(iterations=iterations, implementation_budget_s=impl_budget)


__all__ = ["PatchSizing", "compute_patch_sizing"]
