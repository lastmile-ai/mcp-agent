import asyncio
import time

from mcp_agent.agents.agent import Agent
from mcp_agent.app import MCPApp
from mcp_agent.workflows.llm.augmented_llm_openai import OpenAIAugmentedLLM


# Settings can either be specified programmatically,
# or loaded from mcp_agent.config.yaml/mcp_agent.secrets.yaml.
app = MCPApp(name="mcp_xquik")


async def example_usage() -> None:
    """Discover a read-only Xquik endpoint with an MCP agent."""
    async with app.run() as agent_app:
        logger = agent_app.logger

        logger.info("Loaded Xquik MCP config", data={"server_names": ["xquik"]})

        agent = Agent(
            name="xquik-agent",
            instruction="""You use the Xquik MCP server for X/Twitter research tasks.
            Use the explore tool to find endpoint paths before calling live APIs.
            Keep write actions behind explicit human approval.
            """,
            server_names=["xquik"],
        )

        async with agent:
            logger.info("xquik-agent: Connected to Xquik, calling list_tools...")
            tools = await agent.list_tools()
            logger.info("Tools available:", data=tools.model_dump())

            llm = await agent.attach_llm(OpenAIAugmentedLLM)
            result = await llm.generate(
                message=(
                    "Use Xquik to find a read-only endpoint for searching recent "
                    "X/Twitter posts about AI agents. Return the endpoint path "
                    "and the required query fields. Do not execute a write action."
                ),
            )
            logger.info(f"Xquik endpoint plan: {result}")


if __name__ == "__main__":
    start = time.time()
    asyncio.run(example_usage())
    end = time.time()
    t = end - start

    print(f"Total run time: {t:.2f}s")
