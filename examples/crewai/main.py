import asyncio
import time
from dotenv import load_dotenv

from mcp_agent.app import MCPApp
from mcp_agent.agents.agent import Agent
from mcp_agent.tools.crewai_tool import from_crewai_tool
from mcp_agent.workflows.llm.augmented_llm_openai import OpenAIAugmentedLLM
from crewai_tools import SerperDevTool, FileWriterTool

# Load env variables
load_dotenv()

app = MCPApp(name="search_example")


async def example_usage():
    async with app.run() as agent_app:
        logger = agent_app.logger

        # Instantiate tool
        search_tool = SerperDevTool()
        file_tool = FileWriterTool()

        search_agent = Agent(
            name="search_agent",
            instruction="""You are a helpful assistant""",
            server_names=[],
            functions=[from_crewai_tool(search_tool), from_crewai_tool(file_tool)],
        )

        async with search_agent:
            llm = await search_agent.attach_llm(OpenAIAugmentedLLM)

            result = await llm.generate_str(
                message="What is Singapore's favorite dish? Write a haiku about it in ./haiku.md",
            )

            logger.info(f"Result: {result}")


if __name__ == "__main__":
    start = time.time()
    asyncio.run(example_usage())
    end = time.time()
    t = end - start

    print(f"Total run time: {t:.2f}s")
