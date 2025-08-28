"""
Workflow MCP Server Example

This example demonstrates three approaches to creating agents and workflows:
1. Traditional workflow-based approach with manual agent creation
2. Programmatic agent configuration using AgentConfig
3. Declarative agent configuration using FastMCPApp decorators
"""

import asyncio
import logging

import yaml
from mcp.server.fastmcp import FastMCP

from mcp_agent.app import MCPApp
from mcp_agent.config import Settings, LoggerSettings, MCPSettings, MCPServerSettings
from mcp_agent.server.app_server import create_mcp_server_for_app
from mcp_agent.agents.agent import Agent
from mcp_agent.workflows.llm.augmented_llm_openai import OpenAIAugmentedLLM
from mcp_agent.executor.workflow import Workflow, WorkflowResult

# Initialize logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Note: This is purely optional:
# if not provided, a default FastMCP server will be created by MCPApp using create_mcp_server_for_app()
mcp = FastMCP(name="haiku_generation_server", description="Server to generate haikus")

# Create settings explicitly, as we want to use a different configuration from the main app
secrets_file = Settings.find_secrets()
if secrets_file and secrets_file.exists():
    with open(secrets_file, "r", encoding="utf-8") as f:
        yaml_secrets = yaml.safe_load(f) or {}
        openai_secret = yaml_secrets["openai"]

settings = Settings(
    execution_engine="asyncio",
    logger=LoggerSettings(type="console", level="debug"),
    mcp=MCPSettings(
        servers={
            "haiku_server": MCPServerSettings(
                command="uv",
                args=["run", "nested_server.py"],
                description="nested server providing a haiku generator"
            )
        }
    ),
    openai=openai_secret
)

# Define the MCPApp instance
app = MCPApp(
    name="haiku_server",
    description="Haiku server",
    mcp=mcp,
    settings=settings
)


@app.workflow
class HaikuWorkflow(Workflow[str]):
    """
    A workflow that generates haikus on request.
    """

    @app.workflow_run
    async def run(self, input: str) -> WorkflowResult[str]:
        """
        Run the haiku agent workflow.

        Args:
            input: The topic to create a haiku about

        Returns:
            WorkflowResult containing the processed data.
        """

        logger = app.logger

        haiku_agent = Agent(
            name="poet",
            instruction="""You are an agent with access to a tool that helps you write
            haikus.""",
            server_names=["haiku_server"],
        )

        async with haiku_agent:
            llm = await haiku_agent.attach_llm(OpenAIAugmentedLLM)

            result = await llm.generate_str(
                message=f"Write a haiku about {input} using the tool at your disposal",
            )
            logger.info(f"Input: {input}, Result: {result}")

            return WorkflowResult(value=result)


async def main():
    async with app.run() as agent_app:
        # Log registered workflows and agent configurations
        logger.info(f"Creating MCP server for {agent_app.name}")

        logger.info("Registered workflows:")
        for workflow_id in agent_app.workflows:
            logger.info(f"  - {workflow_id}")

        # Create the MCP server that exposes both workflows and agent configurations
        mcp_server = create_mcp_server_for_app(agent_app, **({}))
        logger.info(f"MCP Server settings: {mcp_server.settings}")

        # Run the server
        await mcp_server.run_stdio_async()


if __name__ == "__main__":
    asyncio.run(main())