import asyncio
import pathlib
import tempfile

import httpx

from mcp_agent.registry.loader import LoaderConfig, ToolRegistryLoader, load_inventory
from mcp_agent.registry.models import ToolSource


def _write_inventory(data) -> str:
    with tempfile.NamedTemporaryFile("w", delete=False, suffix=".yaml") as handle:
        handle.write(data)
        return handle.name


def test_load_inventory_parses_and_sorts():
    yaml_content = """
tools:
  - id: beta
    name: Beta
    base_url: http://b.example
    tags: [two]
  - id: alpha
    name: Alpha
    base_url: http://a.example
    tags: [one]
"""
    config = LoaderConfig(tools_yaml_path=_write_inventory(yaml_content))
    sources = load_inventory(config)
    assert [source.id for source in sources] == ["alpha", "beta"]
    assert sources[0].tags == ["one"]


def test_probe_collects_metadata(monkeypatch):
    source = ToolSource(
        id="test",
        name="Test",
        base_url="http://svc.local",
        headers={},
        tags=["demo"],
    )
    loader = ToolRegistryLoader()

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/.well-known/mcp"):
            return httpx.Response(
                200,
                json={
                    "name": "Example",
                    "version": "1.2.3",
                    "capabilities": ["tools.list", "tools.call"],
                },
            )
        if request.url.path.endswith("/health"):
            return httpx.Response(200, json={"status": "ok"})
        return httpx.Response(404)

    transport = httpx.MockTransport(handler)

    def build_client(self):
        return httpx.AsyncClient(transport=transport)

    monkeypatch.setattr(ToolRegistryLoader, "_build_client", build_client, raising=False)
    async def run():
        result = await loader.probe(source)
        return result

    result = asyncio.run(run())
    assert result.name == "Example"
    assert result.version == "1.2.3"
    assert result.alive is True
    assert result.capabilities == ["tools.call", "tools.list"]
    assert result.failure_reason is None


def test_probe_failure_marks_reason(monkeypatch):
    source = ToolSource(
        id="bad",
        name="Bad",
        base_url="http://svc.local",
        headers={},
        tags=[],
    )
    loader = ToolRegistryLoader()

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500)

    transport = httpx.MockTransport(handler)

    def build_client(self):
        return httpx.AsyncClient(transport=transport)

    monkeypatch.setattr(ToolRegistryLoader, "_build_client", build_client, raising=False)
    async def run():
        return await loader.probe(source)

    result = asyncio.run(run())
    assert result.failure_reason is not None
    assert result.capabilities == []
    assert result.alive is False
