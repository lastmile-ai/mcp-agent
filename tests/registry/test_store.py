import asyncio
from datetime import datetime, timedelta, timezone

from mcp_agent.registry.models import ToolProbeResult, ToolSource
from mcp_agent.registry.store import ToolRegistryStore


class StubLoader:
    def __init__(self, sources, results):
        self._sources = sources
        self._results = results
        self.calls = 0

    def load_sources(self):
        return self._sources

    async def probe(self, source):
        index = self.calls
        self.calls += 1
        return self._results[index]


def _ts(offset: int = 0) -> datetime:
    return datetime.now(timezone.utc) + timedelta(seconds=offset)


def test_store_refresh_handles_success_and_failure():
    source = ToolSource(
        id="github",
        name="GitHub",
        base_url="http://github",
        headers={},
        tags=["scm"],
    )
    success_probe = ToolProbeResult(
        id="github",
        name="GitHub MCP",
        version="1.2.3",
        base_url=source.base_url,
        alive=True,
        latency_ms=12.3,
        capabilities=["tools.call"],
        tags=source.tags,
        timestamp=_ts(),
        failure_reason=None,
    )
    failure_probe = ToolProbeResult(
        id="github",
        name="GitHub MCP",
        version="1.2.3",
        base_url=source.base_url,
        alive=False,
        latency_ms=20.0,
        capabilities=[],
        tags=source.tags,
        timestamp=_ts(10),
        failure_reason="timeout",
    )

    loader = StubLoader([source], [success_probe, failure_probe])
    store = ToolRegistryStore(loader=loader, refresh_interval_sec=5, stale_max_sec=120, enabled=False)

    async def run_cycle():
        return await store.refresh(force=True)

    snapshot = asyncio.run(run_cycle())
    assert snapshot.items[0].alive is True
    assert snapshot.items[0].capabilities == ["tools.call"]
    assert store.ever_succeeded is True

    snapshot = asyncio.run(run_cycle())
    item = snapshot.items[0]
    assert item.alive is False
    # capabilities should be retained from the last good probe
    assert item.capabilities == ["tools.call"]
    assert item.consecutive_failures == 1
    assert item.failure_reason == "timeout"
