"""
Example MCP Agent application showing simplified agent access.
"""

import asyncio
from mcp_agent.core.decorator_app import MCPAgentDecorator

# Create the application
agent_app = MCPAgentDecorator("root-test")


# Define the agent
@agent_app.agent(
    name="basic_agent",
    instruction="A simple agent that helps with basic tasks.",
    servers=["mcp_root"],
)
async def main():
    # Use the app's context manager
    async with agent_app.run() as agent:
        result = await agent.send("basic_agent", "what's the next  number?")
        print("\n\n\n" + result)


if __name__ == "__main__":
    asyncio.run(main())
