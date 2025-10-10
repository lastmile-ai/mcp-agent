"""Heuristic estimator that predicts the LLM-time budget for a feature."""

from __future__ import annotations

from dataclasses import dataclass

from .models import BudgetEstimate, FeatureSpec

BASELINE_SECONDS_PER_ITERATION = 120
MIN_ITERATIONS = 4
MAX_ITERATIONS = 7


@dataclass
class EstimationBreakdown:
    complexity_score: float
    risk_multiplier: float
    iterations: int

    def summary(self) -> str:
        return (
            f"complexity={self.complexity_score:.2f}, "
            f"risk={self.risk_multiplier:.2f}, "
            f"iterations={self.iterations}"
        )


def _complexity(spec: FeatureSpec) -> float:
    size = max(len(spec.summary.split()) + len(spec.details.split()), 1)
    target_weight = 0.4 * len(spec.targets)
    detail_weight = min(size / 250.0, 3.0)
    return 1.0 + target_weight + detail_weight


def _risk(spec: FeatureSpec) -> float:
    multiplier = 1.0
    joined = " ".join(spec.risks + [spec.summary, spec.details]).lower()
    if "security" in joined or "auth" in joined:
        multiplier += 0.25
    if "migration" in joined or "database" in joined:
        multiplier += 0.25
    if "payment" in joined:
        multiplier += 0.15
    multiplier += 0.1 * len(spec.risks)
    return min(multiplier, 2.0)


def _iterations(score: float, multiplier: float) -> int:
    guess = round(score * multiplier)
    return max(MIN_ITERATIONS, min(MAX_ITERATIONS, guess))


def _caps(iterations: int, spec: FeatureSpec) -> dict[str, int]:
    return {
        "max_iterations": iterations,
        "max_repairs": max(1, iterations - 2),
        "max_parallel_checks": max(1, min(3, len(spec.targets) + 1)),
    }


def estimate_budget(spec: FeatureSpec) -> BudgetEstimate:
    complexity = _complexity(spec)
    risk = _risk(spec)
    iterations = _iterations(complexity, risk)
    seconds = int(iterations * BASELINE_SECONDS_PER_ITERATION * risk)
    breakdown = EstimationBreakdown(complexity, risk, iterations)
    rationale = "Estimated from draft spec: " + breakdown.summary()
    return BudgetEstimate(seconds=seconds, rationale=rationale, iterations=iterations, caps=_caps(iterations, spec))


__all__ = ["estimate_budget", "EstimationBreakdown"]
