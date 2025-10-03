import asyncio
import time
from dotenv import load_dotenv

from mcp_agent.app import MCPApp
from mcp_agent.agents.agent import Agent
from mcp_agent.tools.langchain_tool import from_langchain_tool
from mcp_agent.workflows.llm.augmented_llm_openai import OpenAIAugmentedLLM
from langchain_community.utilities import GoogleSerperAPIWrapper

# Load env variables
load_dotenv()

app = MCPApp(name="search_example")


async def example_usage():
    async with app.run() as agent_app:
        logger = agent_app.logger

        search_tool = GoogleSerperAPIWrapper()

        finder_agent = Agent(
            name="search_agent",
            instruction="""You are a helpful assistant""",
            server_names=[],
            functions=[from_langchain_tool(search_tool)],
        )

        async with finder_agent:
            llm = await finder_agent.attach_llm(OpenAIAugmentedLLM)

            result = await llm.generate_str(
                message="Who is Singapore's current prime minister?",
            )

            logger.info(f"result: {result}")


if __name__ == "__main__":
    start = time.time()
    asyncio.run(example_usage())
    end = time.time()
    t = end - start

    print(f"Total run time: {t:.2f}s")
