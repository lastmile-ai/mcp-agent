import asyncio
import time

from mcp_agent.app import MCPApp
from mcp_agent.agents.agent import Agent


# Settings can either be specified programmatically,
# or loaded from mcp_agent.config.yaml/mcp_agent.secrets.yaml
app = MCPApp(name="mcp_streamable_http")


async def example_usage():
    async with app.run() as agent_app:
        logger = agent_app.logger
        context = agent_app.context

        logger.info("Current config:", data=context.config.model_dump())

        agent = Agent(
            name="streamable-http-agent",
            instruction="""You are an agent whose job is to interact with various MCP servers over
            streamable HTTP transport.
            """,
            server_names=["stateless_http"],
        )

        async with agent:
            logger.info(
                "streamable-http-agent: Connected to servers, calling list_tools..."
            )
            result = await agent.list_tools()
            logger.info("Tools available:", data=result.model_dump())

            session_id = (await agent.get_server_session("stateless_http")).session_id
            logger.info(
                "Session ID:", data=session_id
            )  # Expected to be None for stateless server


if __name__ == "__main__":
    start = time.time()
    asyncio.run(example_usage())
    end = time.time()
    t = end - start

    print(f"Total run time: {t:.2f}s")
