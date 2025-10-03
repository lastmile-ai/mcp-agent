import asyncio

from dotenv import load_dotenv
from rich import print
from mcp.types import CallToolResult
from mcp_agent.agents.agent import Agent
from mcp_agent.app import MCPApp

load_dotenv()  # load environment variables from .env


async def test_sse():
    app: MCPApp = MCPApp(name="test-app")
    async with app.run():
        print("MCP App initialized.")

        agent: Agent = Agent(
            name="agent",
            instruction="You are an assistant",
            server_names=["mcp_test_server_sse"],
        )

        original_number = 1

        async with agent:
            print(await agent.list_tools())
            call_tool_result: CallToolResult = await agent.call_tool(
                "mcp_test_server_sse_get-magic-number",
                {"original_number": original_number},
            )

            assert call_tool_result.content[0].text == str(42 + original_number)
            print("SSE test passed!")


if __name__ == "__main__":
    asyncio.run(test_sse())
