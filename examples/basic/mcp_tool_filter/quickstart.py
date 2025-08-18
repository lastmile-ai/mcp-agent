#!/usr/bin/env python3
"""
Quickstart example for MCP Tool Filter

This is the minimal code needed to use tool filtering.
"""

import asyncio
import os
from mcp_agent.app import MCPApp
from mcp_agent.agents.agent import Agent
from mcp_agent.workflows.llm.augmented_llm_openai import OpenAIAugmentedLLM
from mcp_agent.utils.tool_filter import ToolFilter, apply_tool_filter


async def main():
    # Create app
    app = MCPApp(name="quickstart")

    async with app.run() as agent_app:
        context = agent_app.context

        # Configure filesystem server
        if "filesystem" in context.config.mcp.servers:
            cwd = os.getcwd()
            if cwd not in context.config.mcp.servers["filesystem"].args:
                context.config.mcp.servers["filesystem"].args.append(cwd)

        # Create agent
        agent = Agent(
            name="my_agent",
            instruction="You are a helpful assistant.",
            server_names=["filesystem"],
        )

        async with agent:
            # Attach LLM
            llm = await agent.attach_llm(OpenAIAugmentedLLM)

            # Apply filter - only allow read operations
            filter = ToolFilter(
                allowed=["filesystem_read_file", "filesystem_list_directory"]
            )
            apply_tool_filter(llm, filter)

            # Use the filtered LLM
            result = await llm.generate_str("What files are in the current directory?")
            print(f"\nResult: {result}")


if __name__ == "__main__":
    asyncio.run(main())
