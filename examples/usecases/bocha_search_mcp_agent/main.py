import asyncio
import os
from pathlib import Path

from mcp_agent.app import MCPApp
from mcp_agent.mcp.mcp_aggregator import MCPAggregator
from rich import print


app = MCPApp(name="bocha_search_mcp_agent")


def bocha_server_config_from_process() -> tuple[list[str], dict[str, str]]:
    server_dir = os.environ.get("BOCHA_SEARCH_MCP_DIR")
    api_key = os.environ.get("BOCHA_API_KEY")

    if not server_dir:
        raise RuntimeError("BOCHA_SEARCH_MCP_DIR is required in the current shell")
    if not api_key:
        raise RuntimeError("BOCHA_API_KEY is required in the current shell")

    server_path = Path(server_dir)
    if not server_path.exists() or not server_path.is_dir():
        raise RuntimeError(
            "BOCHA_SEARCH_MCP_DIR does not exist or is not a directory: "
            f"{server_dir}"
        )

    return (
        ["--directory", str(server_path), "run", "bocha-search-mcp"],
        {"BOCHA_API_KEY": api_key},
    )


def raise_for_bocha_error(result: object) -> None:
    for item in getattr(result, "content", []):
        text = getattr(item, "text", "")
        if "API HTTP error occurred" in text or "Invalid API KEY" in text:
            raise RuntimeError(f"Bocha search failed: {text}")


def find_bocha_search_tool(tool_names: list[str]) -> str:
    search_tool = next(
        (name for name in tool_names if name.endswith("bocha_web_search")),
        None,
    )
    if not search_tool:
        raise RuntimeError(
            f"No 'bocha_web_search' tool found; available tools: {tool_names}"
        )
    return search_tool


async def search_bocha(query: str = "Bocha Search MCP test") -> str:
    async with app.run() as running_app:
        args, env = bocha_server_config_from_process()
        server_config = running_app.context.config.mcp.servers["bocha"]
        server_config.args = args
        server_config.env = env

        aggregator = await MCPAggregator.create(
            server_names=["bocha"],
            connection_persistence=False,
        )

        try:
            tools = await aggregator.list_tools()
            tool_names = [tool.name for tool in tools.tools]
            print("[bold]Bocha MCP tools discovered:[/bold]", tool_names)

            search_tool = find_bocha_search_tool(tool_names)
            result = await aggregator.call_tool(
                name=search_tool,
                arguments={
                    "query": query,
                    "freshness": "noLimit",
                    "count": 3,
                },
            )
            raise_for_bocha_error(result)
            print("[bold]Bocha search result:[/bold]")
            print(result)
            return str(result)
        finally:
            await aggregator.close()


if __name__ == "__main__":
    asyncio.run(search_bocha())
