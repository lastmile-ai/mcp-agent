"""
NVIDIA NIM Basic Agent Example

This example demonstrates using NVIDIA NIM with mcp-agent.
It shows:
- Connecting to the NVIDIA API catalog (or a self-hosted NIM)
- Using the filesystem MCP server for tool calling
- Running queries with the nvidia/nemotron-3.5-super-vl-120b-a12b model
- Multi-turn conversations with context

Prerequisites:
1. Get an API key from https://build.nvidia.com
2. Set the NVIDIA_API_KEY environment variable
3. Optionally set nvidia.base_url to a self-hosted NIM (default: https://integrate.api.nvidia.com/v1)
"""

import asyncio
import os

from mcp_agent.app import MCPApp
from mcp_agent.agents.agent import Agent
from mcp_agent.workflows.llm.augmented_llm_nvidia import NvidiaAugmentedLLM

# Create the app - configuration will be loaded from mcp_agent.config.yaml
app = MCPApp(name="nvidia_basic_agent")


async def example_usage():
    """
    Example showing NVIDIA agent using filesystem tools.
    """
    async with app.run() as agent_app:
        logger = agent_app.logger
        context = agent_app.context

        logger.info("Starting NVIDIA example...")
        logger.info(
            "NVIDIA config:",
            data=context.config.nvidia.model_dump(exclude={"api_key"}),
        )

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

            llm = await file_agent.attach_llm(NvidiaAugmentedLLM)
            logger.info(
                f"Using NVIDIA with model: {context.config.nvidia.default_model}"
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
    Example showing structured outputs with NVIDIA.
    Important: Not all models are capable of structured output, particularly LLMs below 7B parameters.
    Check the model card on build.nvidia.com if you are unsure if the model supports structured output.
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
            llm = await agent.attach_llm(NvidiaAugmentedLLM)

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
        print("1. NVIDIA_API_KEY is set (get a key at https://build.nvidia.com)")
        print(
            "2. nvidia.default_model in mcp_agent.config.yaml is a model available to you"
        )
        raise


if __name__ == "__main__":
    asyncio.run(main())
