import asyncio

from dotenv import load_dotenv
from rich import print

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

        async with agent:
            print(await agent.list_tools())
            # call_tool_result: CallToolResult = await agent.call_tool('mcp_test_server_sse-get-magic-number')
            #
            # assert call_tool_result.text == "42"
            # print("SSE test passed!")


if __name__ == "__main__":
    asyncio.run(test_sse())
