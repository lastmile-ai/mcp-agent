"""
VMware AIops Agent — mcp-agent example

Demonstrates using mcp-agent with vmware-aiops MCP server to monitor and
manage VMware vCenter/ESXi infrastructure via natural language.

Prerequisites:
  1. uv tool install vmware-aiops
  2. Configure ~/.vmware-aiops/config.yaml and ~/.vmware-aiops/.env
  3. Set ANTHROPIC_API_KEY in environment or mcp_agent.secrets.yaml
  4. Update mcp_agent.config.yaml: set cwd to your VMware-AIops clone path
"""

import asyncio

from mcp_agent.app import MCPApp
from mcp_agent.agents.agent import Agent
from mcp_agent.workflows.llm.augmented_llm import RequestParams
from mcp_agent.workflows.llm.augmented_llm_anthropic import AnthropicAugmentedLLM

app = MCPApp(name="vmware_agent")


async def example_usage():
    async with app.run() as agent_app:
        logger = agent_app.logger

        # VMware infrastructure monitoring agent
        vmware_agent = Agent(
            name="vmware-ops",
            instruction=(
                "You are a VMware infrastructure assistant. "
                "Use the available tools to query vCenter/ESXi state, "
                "report health issues, and help manage VMs. "
                "Always confirm before taking destructive actions."
            ),
            server_names=["vmware-aiops"],
        )

        async with vmware_agent:
            logger.info("Connected to vmware-aiops MCP server")

            llm = await vmware_agent.attach_llm(AnthropicAugmentedLLM)

            # Example 1: Infrastructure health overview
            logger.info("--- Example 1: Health overview ---")
            result = await llm.generate_str(
                message="Show me all active alarms and summarize by severity.",
                request_params=RequestParams(model="claude-sonnet-4-6"),
            )
            logger.info(f"Health report:\n{result}")

            # Example 2: VM inventory
            logger.info("--- Example 2: VM inventory ---")
            result = await llm.generate_str(
                message="List all powered-on VMs sorted by memory usage, show top 5.",
                request_params=RequestParams(model="claude-sonnet-4-6"),
            )
            logger.info(f"VM inventory:\n{result}")

            # Example 3: Multi-turn — investigate an issue
            logger.info("--- Example 3: Multi-turn investigation ---")
            result = await llm.generate_str(
                message="Are there any datastores above 80% capacity?",
                request_params=RequestParams(model="claude-sonnet-4-6"),
            )
            logger.info(f"Datastore check:\n{result}")

            result = await llm.generate_str(
                message="For the most critical one, which VMs are on it and how large are they?",
                request_params=RequestParams(model="claude-sonnet-4-6"),
            )
            logger.info(f"Datastore detail:\n{result}")


if __name__ == "__main__":
    import time

    start = time.time()
    asyncio.run(example_usage())
    end = time.time()
    print(f"\nTotal run time: {end - start:.2f}s")
