import pytest

from mcp_agent.github.token_manager import TokenManager
from mcp_agent.sentinel import client as sentinel_client


@pytest.mark.asyncio
async def test_token_manager_refreshes_when_ttl_low(monkeypatch: pytest.MonkeyPatch) -> None:
    times = iter([1000.0, 1295.0, 1295.0])

    def fake_time() -> float:
        return next(times)

    monkeypatch.setattr("mcp_agent.github.token_manager.time.time", fake_time)

    calls: list[dict] = []
    responses = [
        {"token": "token-1", "expires_at": 1300.0, "granted_permissions": {}},
        {"token": "token-2", "expires_at": 1500.0, "granted_permissions": {}},
    ]

    async def fake_issue_github_token(**kwargs):
        calls.append(kwargs)
        return responses[len(calls) - 1]

    monkeypatch.setattr(sentinel_client, "issue_github_token", fake_issue_github_token)

    manager = TokenManager("org/repo")

    first = await manager.ensure_valid(min_required_ttl_s=100)
    assert first.token == "token-1"
    assert calls[0]["ttl_seconds"] == 200

    second = await manager.ensure_valid(min_required_ttl_s=90)
    assert second.token == "token-1"
    assert len(calls) == 1

    third = await manager.ensure_valid(min_required_ttl_s=100)
    assert third.token == "token-2"
    assert len(calls) == 2
    assert calls[1]["ttl_seconds"] == 200
