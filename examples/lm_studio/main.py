"""
LM Studio Basic Agent Example

This example demonstrates using LM Studio with mcp-agent to run local models.
It shows:
- Connecting to LM Studio's local server
- Using the filesystem MCP server for tool calling
- Running queries with the openai/gpt-oss-20b model
- Multi-turn conversations with context

Prerequisites:
1. Install and run LM Studio (https://lmstudio.ai)
2. Download and load the openai/gpt-oss-20b model in LM Studio
3. Start the LM Studio server (default: http://localhost:1234)
"""

import asyncio
import os

from mcp_agent.app import MCPApp
from mcp_agent.agents.agent import Agent
from mcp_agent.workflows.llm.augmented_llm_lm_studio import LMStudioAugmentedLLM

# Create the app - configuration will be loaded from mcp_agent.config.yaml
app = MCPApp(name="lmstudio_basic_agent")


async def example_usage():
    """
    Example showing LM Studio agent using filesystem tools.
    """
    async with app.run() as agent_app:
        logger = agent_app.logger
        context = agent_app.context

        logger.info("Starting LM Studio example...")
        logger.info("LM Studio config:", data=context.config.lm_studio.model_dump())

        # Add the current directory to the filesystem server
        context.config.mcp.servers["filesystem"].args.extend([os.getcwd()])

        # Create an agent with filesystem access
        file_agent = Agent(
            name="file_explorer",
            instruction="""You are a helpful assistant with access to the local filesystem.
            You can read files, list directories, and answer questions about file contents.
            Always be clear about what files you're accessing.""",
            server_names=["filesystem"],
        )

        async with file_agent:
            tools = await file_agent.list_tools()
            logger.info(
                f"Agent has {len(tools.tools)} tools available:",
                data=[tool.name for tool in tools.tools],
            )

            llm = await file_agent.attach_llm(LMStudioAugmentedLLM)
            logger.info(
                f"Using LM Studio with model: {context.config.lm_studio.default_model}"
            )

            logger.info("\n--- Example 1: Reading config file ---")
            result = await llm.generate_str(
                "Read the mcp_agent.config.yaml file and tell me what MCP servers are configured."
            )
            logger.info("Agent response:", data=result)

            logger.info("\n--- Example 2: Listing files ---")
            result = await llm.generate_str(
                "List all Python files (.py) in the current directory and tell me what they are."
            )
            logger.info("Agent response:", data=result)

            logger.info("\n--- Example 3: Multi-turn conversation ---")
            result = await llm.generate_str(
                "What is the name of the main Python file in this directory?"
            )
            logger.info("Turn 1 response:", data=result)

            result = await llm.generate_str(
                "Can you read that file and summarize what it does in 2 sentences?"
            )
            logger.info("Turn 2 response:", data=result)

            logger.info("\n--- Example completed successfully! ---")


async def structured_output_example():
    """
    Example showing structured outputs with LM Studio.
    """
    from pydantic import BaseModel
    from typing import List

    class FileInfo(BaseModel):
        """Information about files in a directory."""

        file_names: List[str]
        file_count: int
        has_readme: bool

    async with app.run() as agent_app:
        logger = agent_app.logger
        context = agent_app.context

        logger.info("\n--- Structured Output Example ---")

        context.config.mcp.servers["filesystem"].args.extend([os.getcwd()])

        agent = Agent(
            name="structured_agent",
            instruction="You analyze directories and return structured information.",
            server_names=["filesystem"],
        )

        async with agent:
            llm = await agent.attach_llm(LMStudioAugmentedLLM)

            result = await llm.generate_structured(
                message="List all files in the current directory and tell me if there's a README file.",
                response_model=FileInfo,
            )

            logger.info("Structured response:", data=result.model_dump())
            logger.info(f"Found {result.file_count} files")
            logger.info(f"Has README: {result.has_readme}")


async def main():
    """
    Main entry point - runs all examples.
    """
    try:
        await example_usage()
        await structured_output_example()

    except Exception as e:
        print(f"\nError: {e}")
        print("\nMake sure:")
        print("1. LM Studio is running (http://localhost:1234)")
        print("2. You have loaded the openai/gpt-oss-20b model")
        raise


if __name__ == "__main__":
    asyncio.run(main())
