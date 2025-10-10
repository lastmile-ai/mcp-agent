import asyncio
import json
from importlib import import_module

from mcp.types import CallToolResult, ListToolsResult, TextContent, Tool


toolkit_mod = import_module("mcp_agent.context.toolkit")


class StubAggregator:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict | None]] = []
        self.server_names = ["search"]

    async def initialize(self) -> None:  # pragma: no cover - compatibility shim
        return None

    async def list_servers(self):
        return list(self.server_names)

    async def list_tools(self, server_name: str | None = None) -> ListToolsResult:
        assert server_name in (None, "search")
        tool = Tool(name="search_semantic_search", inputSchema={"version": "1"})
        return ListToolsResult(tools=[tool])

    async def call_tool(self, name: str, arguments: dict | None = None) -> CallToolResult:
        self.calls.append((name, arguments))
        payload = {
            "spans": [
                {
                    "uri": "file:///z.py",
                    "start": 0,
                    "end": 10,
                    "section": 3,
                    "priority": 1,
                }
            ]
        }
        return CallToolResult(content=[TextContent(type="text", text=json.dumps(payload))])


def test_aggregator_toolkit_semantic_search_uses_fqn():
    aggregator = StubAggregator()
    toolkit = toolkit_mod.AggregatorToolKit(trace_id="trace", repo_sha="sha", aggregator=aggregator)

    spans = asyncio.run(toolkit.semantic_search("query", 5))
    assert spans
    assert spans[0].tool == "search.semantic_search"

    assert aggregator.calls
    name, args = aggregator.calls[0]
    assert name == "search_semantic_search"
    assert args["trace_id"] == "trace"
    assert args["repo_sha"] == "sha"

    versions = asyncio.run(toolkit.tool_versions())
    assert versions == {"search.semantic_search": "1"}
