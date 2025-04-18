import argparse
import asyncio
import time

from rich import print

from mcp_agent.app import MCPApp
from mcp_agent.agents.agent import Agent
from mcp_agent.workflows.llm.augmented_llm_openai import OpenAIAugmentedLLM


# Settings can either be specified programmatically,
# or loaded from mcp_agent.config.yaml/mcp_agent.secrets.yaml
app = MCPApp(name="mcp_websockets")  # settings=settings)


async def example_usage(username: str):
    async with app.run() as agent_app:
        logger = agent_app.logger
        context = agent_app.context

        logger.info("Current config:", data=context.config.model_dump())

        agent = Agent(
            name="github-agent",
            instruction="""You are an agent whose job is to interact with the Github
            repository for the user.
            """,
            server_names=["smithery-github"],
        )

        async with agent:
            logger.info("github-agent: Connected to server, calling list_tools...")
            result = await agent.list_tools()
            logger.info("Tools available:", data=result.model_dump())

            llm = await agent.attach_llm(OpenAIAugmentedLLM)
            result = await llm.generate_str(
                message=f"List all public Github repositories created by the user {username}.",
            )
            print(f"Github repositories: {result}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("username", help="GitHub username to fetch repositories for")

    args = parser.parse_args()

    start = time.time()
    asyncio.run(example_usage(args.username))
    end = time.time()
    t = end - start

    print(f"Total run time: {t:.2f}s")
