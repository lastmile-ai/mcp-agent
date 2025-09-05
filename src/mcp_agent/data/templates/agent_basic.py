#!/usr/bin/env python3
"""Basic MCP-Agent example."""

from mcp_agent.app import MCPApp
from mcp_agent.agents.agent_spec import AgentSpec

# Create the MCP application
app = MCPApp("My Agent")

# Define an agent with access to filesystem
my_agent = AgentSpec(
    name="assistant",
    instruction="You are a helpful AI assistant with access to the filesystem.",
    server_names=["filesystem"],
)

# Register the agent with the app
app.register_agent("assistant", my_agent)


if __name__ == "__main__":
    import asyncio
    from mcp_agent.workflows.factory import create_llm

    async def main():
        """Run the agent interactively."""
        async with app.run():
            # Create an LLM for the agent
            llm = create_llm(
                agent_name="assistant",
                server_names=["filesystem"],
                instruction=my_agent.instruction,
                context=app.context,
            )

            # Start interactive chat
            print("Chat with your agent (Ctrl+C to exit)")
            print("Type your message and press Enter:\n")

            while True:
                try:
                    message = input("> ")
                    if message.strip():
                        response = await llm.generate_str(message)
                        print(f"\nAssistant: {response}\n")
                except KeyboardInterrupt:
                    break
                except Exception as e:
                    print(f"Error: {e}")

    asyncio.run(main())
