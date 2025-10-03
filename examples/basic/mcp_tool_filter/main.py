"""
MCP Tool Filter Example

This example demonstrates how to filter MCP tools without modifying any core code.
"""

import asyncio
import os

from mcp_agent.app import MCPApp
from mcp_agent.agents.agent import Agent
from mcp_agent.workflows.llm.augmented_llm_openai import OpenAIAugmentedLLM
from mcp_agent.utils.tool_filter import ToolFilter, apply_tool_filter


app = MCPApp(name="mcp_tool_filter")


async def example_1_basic_filtering():
    """Example 1: Basic tool filtering with allowed list"""
    print("\n=== Example 1: Basic Filtering (Whitelist) ===")

    async with app.run() as agent_app:
        logger = agent_app.logger
        context = agent_app.context

        # Configure filesystem server
        if "filesystem" in context.config.mcp.servers:
            cwd = os.getcwd()
            if cwd not in context.config.mcp.servers["filesystem"].args:
                context.config.mcp.servers["filesystem"].args.append(cwd)

        # Create agent
        agent = Agent(
            name="filtered_agent",
            instruction="You are a helpful file assistant.",
            server_names=["filesystem"],
        )

        async with agent:
            # Create LLM
            llm = await agent.attach_llm(OpenAIAugmentedLLM)

            # Apply filter - only allow read operations
            filter = ToolFilter(
                allowed=["filesystem_read_file", "filesystem_list_directory"]
            )
            apply_tool_filter(llm, filter)

            logger.info("Filter applied: Only read operations allowed")

            # Test with a read task
            result = await llm.generate_str(
                "Please list the files in the current directory."
            )
            logger.info(f"Result: {result}")


async def example_2_excluded_filter():
    """Example 2: Filter using excluded list (blacklist)"""
    print("\n=== Example 2: Excluded List Filter (Blacklist) ===")

    async with app.run() as agent_app:
        logger = agent_app.logger
        context = agent_app.context

        if "filesystem" in context.config.mcp.servers:
            cwd = os.getcwd()
            if cwd not in context.config.mcp.servers["filesystem"].args:
                context.config.mcp.servers["filesystem"].args.append(cwd)

        agent = Agent(
            name="safe_agent",
            instruction="You are a safe file assistant that cannot delete or modify files.",
            server_names=["filesystem"],
        )

        async with agent:
            llm = await agent.attach_llm(OpenAIAugmentedLLM)

            # Exclude dangerous operations
            filter = ToolFilter(
                excluded=[
                    "filesystem_write_file",
                    "filesystem_delete_file",
                    "filesystem_move_file",
                ]
            )
            apply_tool_filter(llm, filter)

            logger.info("Filter applied: Write/delete operations excluded")

            # Demonstrate filtering through actual LLM interaction
            # This shows what tools the LLM actually sees
            result = await llm.generate_str(
                "Please list all the tools you have available. "
                "For each tool, briefly describe what it does."
            )
            logger.info(f"LLM's view of available tools:\n{result}")

            # Try to use an excluded tool (should fail gracefully)
            result = await llm.generate_str(
                "Try to create a file called test.txt with some content."
            )
            logger.info(f"Attempt to use excluded tool:\n{result}")


async def example_3_server_specific():
    """Example 3: Different filters for different servers"""
    print("\n=== Example 3: Server-Specific Filtering ===")

    async with app.run() as agent_app:
        logger = agent_app.logger
        context = agent_app.context

        if "filesystem" in context.config.mcp.servers:
            cwd = os.getcwd()
            if cwd not in context.config.mcp.servers["filesystem"].args:
                context.config.mcp.servers["filesystem"].args.append(cwd)

        # Agent with multiple servers
        agent = Agent(
            name="multi_server_agent",
            instruction="You are an assistant with file and web access.",
            server_names=["filesystem", "fetch"],
        )

        async with agent:
            llm = await agent.attach_llm(OpenAIAugmentedLLM)

            # Server-specific filters
            filter = ToolFilter(
                server_filters={
                    "filesystem": {"allowed": ["read_file", "list_directory"]},
                    "fetch": {"allowed": ["fetch"]},
                }
            )

            apply_tool_filter(llm, filter)

            logger.info("Server-specific filters applied")

            # Test task
            result = await llm.generate_str(
                "Check if there's a README.md file and summarize what this project is about."
            )
            logger.info(f"Result: {result}")


async def example_4_dynamic_filtering():
    """Example 4: Change filters during runtime"""
    print("\n=== Example 4: Dynamic Filtering ===")

    async with app.run() as agent_app:
        logger = agent_app.logger
        context = agent_app.context

        if "filesystem" in context.config.mcp.servers:
            cwd = os.getcwd()
            if cwd not in context.config.mcp.servers["filesystem"].args:
                context.config.mcp.servers["filesystem"].args.append(cwd)

        agent = Agent(
            name="dynamic_agent",
            instruction="You are a helpful assistant.",
            server_names=["filesystem"],
        )

        async with agent:
            llm = await agent.attach_llm(OpenAIAugmentedLLM)

            # Start with read-only
            logger.info("Applying read-only filter...")
            filter1 = ToolFilter(
                allowed=["filesystem_read_file", "filesystem_list_directory"]
            )
            apply_tool_filter(llm, filter1)

            result = await llm.generate_str("List available tools")
            logger.info(f"With read-only filter: {result}")

            # Remove all filters
            logger.info("\nRemoving all filters...")
            apply_tool_filter(llm, None)

            result = await llm.generate_str("List available tools now")
            logger.info(f"Without filter: {result}")


def main():
    """Run examples"""
    print("MCP Tool Filter Examples")
    print("========================")
    print("\nThis demo shows how to filter MCP tools without modifying core code.")
    print("Make sure to set up your API keys in mcp_agent.secrets.yaml\n")

    examples = [
        ("Basic Filtering (Whitelist)", example_1_basic_filtering),
        ("Excluded List Filter (Blacklist)", example_2_excluded_filter),
        ("Server-Specific Filtering", example_3_server_specific),
        ("Dynamic Filtering", example_4_dynamic_filtering),
    ]

    print("Available examples:")
    for i, (name, _) in enumerate(examples, 1):
        print(f"{i}. {name}")

    try:
        choice = (
            input("\nEnter example number (1-4) or 'all' to run all: ").strip().lower()
        )

        if choice == "all":
            print("\nRunning all examples...")
            for _, func in examples:
                print(f"\n{'=' * 60}")
                asyncio.run(func())
        elif choice.isdigit() and 1 <= int(choice) <= len(examples):
            _, func = examples[int(choice) - 1]
            asyncio.run(func())
        else:
            print("Invalid choice. Please run the script again.")
    except KeyboardInterrupt:
        print("\nExiting...")


if __name__ == "__main__":
    main()
