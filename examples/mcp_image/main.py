import asyncio
import time

from mcp_agent.app import MCPApp
from mcp_agent.agents.agent import Agent
from mcp_agent.workflows.llm.augmented_llm_anthropic import AnthropicAugmentedLLM

app = MCPApp(name="mcp_image")

async def example_usage():
    async with app.run() as agent_app:
        logger = agent_app.logger
        context = agent_app.context

        logger.info("Current config:", data=context.config.model_dump())

        agent = Agent(
            name="agent",
            instruction="""You are an agent with access to the computer (with the computer tool). Your job is to identify
            what is on the screen, and describe it in detail.""",
            server_names=["computer"],
            connection_persistence=False
        )

        async with agent:
            logger.info("agent: Connected to server, calling list_tools...")
            result = await agent.list_tools()
            logger.info("Tools available:", data=result.model_dump())

            llm = await agent.attach_llm(AnthropicAugmentedLLM)

            result = await llm.generate(
                message="Take a screenshot of the current screen, and describe what is on it in detail.",

            )
            logger.info(f"Screenshot description: {result}")


if __name__ == "__main__":
    start = time.time()
    asyncio.run(example_usage())
    end = time.time()
    t = end - start

    print(f"Total run time: {t:.2f}s")
