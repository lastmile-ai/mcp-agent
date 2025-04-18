import asyncio
import os

from mcp_agent.app import MCPApp
from mcp_agent.agents.agent import Agent
from mcp_agent.workflows.llm.augmented_llm_openai import OpenAIAugmentedLLM

app = MCPApp(name="mcp_basic_agent")


async def example_usage():
    async with app.run() as agent_app:
        logger = agent_app.logger
        context = agent_app.context

        slack_agent = Agent(
            name="slack_finder",
            instruction="""You are an agent with access to the filesystem, 
            as well as the ability to look up Slack conversations. Your job is to identify 
            the closest match to a user's request, make the appropriate tool calls, 
            and return the results.""",
            server_names=["filesystem", "slack"],
        )

        context.config.mcp.servers["filesystem"].args.extend([os.getcwd()])

        async with slack_agent:
            logger.info("slack: Connected to server, calling list_tools...")
            result = await slack_agent.list_tools()
            logger.info("Tools available:", data=result.model_dump())

            llm = await slack_agent.attach_llm(OpenAIAugmentedLLM)
            result = await llm.generate_str(
                message="What was the last message in the general channel?",
            )
            logger.info(f"Result: {result}")

            # Multi-turn conversations
            result = await llm.generate_str(
                message="Summarize it for me so I can understand it better.",
            )
            logger.info(f"Result: {result}")


if __name__ == "__main__":
    import time

    start = time.time()
    asyncio.run(example_usage())
    end = time.time()
    t = end - start

    print(f"Total run time: {t:.2f}s")
