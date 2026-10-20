"""Discover Dreamtune MCP tools, or invoke one explicitly, without another LLM."""

import argparse
import asyncio
import json
from pathlib import Path

from mcp_agent.agents.agent import Agent
from mcp_agent.app import MCPApp

app = MCPApp(
    name="dreamtune",
    settings=str(Path(__file__).with_name("mcp_agent.config.yaml")),
)


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tool", help="Tool name from the discovery output")
    parser.add_argument("--arguments", default="{}", help="JSON object for --tool")
    options = parser.parse_args()
    try:
        arguments = json.loads(options.arguments)
    except json.JSONDecodeError as error:
        parser.error(str(error))
    if not isinstance(arguments, dict):
        parser.error("--arguments must be a JSON object")

    async with app.run():
        async with Agent(
            name="dreamtune",
            instruction="Use the requested Dreamtune tool with the supplied arguments.",
            server_names=["dreamtune"],
        ) as agent:
            tools = await agent.list_tools()
            if options.tool:
                if options.tool not in {tool.name for tool in tools.tools}:
                    parser.error(
                        "Unknown tool; run without --tool to list available names"
                    )
                result = await agent.call_tool(options.tool, arguments)
                print(result.model_dump_json(indent=2))
                if result.isError:
                    raise SystemExit(1)
            else:
                for tool in tools.tools:
                    print(f"{tool.name}: {tool.description}")


if __name__ == "__main__":
    asyncio.run(main())
