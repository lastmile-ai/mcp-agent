import asyncio
import time

from mcp_agent.app import MCPApp
from mcp_agent.agents.agent import Agent
from mcp_agent.workflows.llm.augmented_llm_openai import OpenAIAugmentedLLM
from mcp_agent.human_input.handler import console_input_callback

# Settings can either be specified programmatically,
# or loaded from mcp_agent.config.yaml/mcp_agent.secrets.yaml
app = MCPApp(
    name="mcp_basic_agent", human_input_callback=console_input_callback
)


async def example_usage():
    async with app.run() as agent_app:
        logger = agent_app.logger

        # --- Example: Using the demo_server MCP server ---
        agent = Agent(
            name="agent",
            instruction="Demo agent for MCP sampling",
            server_names=["demo_server"],    # stdio transport
            # server_names=["demo_server_sse"],  # SSE transport
        )

        async with agent:
            llm = await agent.attach_llm(OpenAIAugmentedLLM)

            # using the MCP server with sampling
            haiku = await llm.generate_str("Write me a haiku about flowers")
            logger.info(f"Generated haiku: {haiku}")

            # not using sampling
            definition = await llm.generate_str("What does the acronym MCP stand for in the context of generative AI?")
            logger.info(f"{definition}")


if __name__ == "__main__":
    start = time.time()
    asyncio.run(example_usage())
    end = time.time()
    t = end - start

    print(f"Total run time: {t:.2f}s")
