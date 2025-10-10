import pytest

from mcp_agent.budget.llm_budget import LLMBudget


def _install_time_sequence(monkeypatch: pytest.MonkeyPatch, *values: float) -> None:
    iterator = iter(values)

    def _fake_time() -> float:
        try:
            return next(iterator)
        except StopIteration:  # pragma: no cover - defensive guard for tests
            return values[-1]

    monkeypatch.setattr("mcp_agent.budget.llm_budget.time.time", _fake_time)


def test_llm_budget_tracks_multiple_windows(monkeypatch: pytest.MonkeyPatch) -> None:
    _install_time_sequence(monkeypatch, 0.0, 0.01, 0.02, 0.05, 0.05, 1.20)

    budget = LLMBudget(limit_seconds=1.0)

    budget.start()
    budget.stop()
    budget.start()
    budget.stop()

    assert budget.active_ms == 40  # 10ms + 30ms
    assert pytest.approx(budget.remaining_seconds(), rel=1e-3) == 0.96
    assert not budget.exceeded()

    budget.start()
    budget.stop()

    assert budget.active_ms == 1190  # previous 40ms + 1150ms
    assert budget.remaining_seconds() == 0.0
    assert budget.exceeded()
