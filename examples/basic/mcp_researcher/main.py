import asyncio
import time
import os
from pathlib import Path

from mcp_agent.app import MCPApp
from mcp_agent.agents.agent import Agent
from mcp_agent.mcp.mcp_connection_manager import MCPConnectionManager
from mcp_agent.workflows.llm.augmented_llm_anthropic import AnthropicAugmentedLLM  # noqa: F401
from mcp_agent.workflows.llm.augmented_llm_openai import OpenAIAugmentedLLM
from mcp_agent.logging.logger import LoggingConfig
from rich import print

app = MCPApp(name="mcp_root_test")


async def example_usage():
    async with app.run() as agent_app:
        folder_path = Path("agent_folder")
        folder_path.mkdir(exist_ok=True)

        context = agent_app.context

        # Overwrite the config because full path to agent folder needs to be passed
        context.config.mcp.servers["interpreter"].args = [
            "run",
            "-i",
            "--rm",
            "--pull=always",
            "-v",
            f"{os.path.abspath('agent_folder')}:/mnt/data/",
            "ghcr.io/evalstate/mcp-py-repl:latest",
        ]

        async with MCPConnectionManager(context.server_registry):
            interpreter_agent = Agent(
                name="research",
                instruction="""You are a research assistant, with access to internet search (via Brave),
                website fetch, a python interpreter (you can install packages with uv) and a filesystem.
                The working directory for the Python Interpreter is shared by the 'Filesystem' tool.
                You can use the working directory to save and create files, and to process them with the Python Interpreter""",
                server_names=["brave", "interpreter", "filesystem", "fetch"],
            )

            research_prompt = """Produce an investment report for the company Eutelsat. The final report should be saved in the filesystem in markdown format, and
                contain at least the following: 
                1 - A brief description of the company
                2 - Current financial position (find data, create and incorporate charts)
                3 - A PESTLE analysis
                4 - An investment thesis for the next 3 years. Include both 'buy side' and 'sell side' arguments, and a final 
                summary and recommendation.
                Todays date is 05 February 2025. Include the main data sources consulted in presenting the report."""

            try:
                llm_oai = await interpreter_agent.attach_llm(OpenAIAugmentedLLM)
                #               llm_anthr = await interpreter_agent.attach_llm(AnthropicAugmentedLLM)  # noqa: F841

                result = await llm_oai.generate_str(research_prompt)
                print(result)

            finally:
                # Clean up the agent
                await interpreter_agent.close()

    # Ensure logging is properly shutdown
    await LoggingConfig.shutdown()


if __name__ == "__main__":
    start = time.time()
    try:
        asyncio.run(example_usage())
    except KeyboardInterrupt:
        print("\nReceived keyboard interrupt, shutting down gracefully...")
    except Exception as e:
        print(f"Error during execution: {e}")
        raise
    finally:
        end = time.time()
        t = end - start
        print(f"Total run time: {t:.2f}s")
