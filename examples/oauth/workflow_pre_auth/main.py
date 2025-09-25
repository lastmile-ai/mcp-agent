"""
Workflow MCP Server Example

This example demonstrates three approaches to creating agents and workflows:
1. Traditional workflow-based approach with manual agent creation
2. Programmatic agent configuration using AgentConfig
3. Declarative agent configuration using FastMCPApp decorators
"""

import argparse
import asyncio
import json
import os
from typing import Dict, Any, Optional
from pydantic import AnyHttpUrl

from mcp.server.fastmcp import FastMCP
from mcp_agent.core.context import Context as AppContext

from mcp_agent.app import MCPApp
from mcp_agent.server.app_server import create_mcp_server_for_app
from mcp_agent.agents.agent import Agent
from mcp_agent.workflows.llm.augmented_llm import RequestParams
from mcp_agent.workflows.llm.llm_selector import ModelPreferences
from mcp_agent.workflows.llm.augmented_llm_anthropic import AnthropicAugmentedLLM
from mcp_agent.workflows.llm.augmented_llm_openai import OpenAIAugmentedLLM
from mcp_agent.workflows.parallel.parallel_llm import ParallelLLM
from mcp_agent.executor.workflow import Workflow, WorkflowResult
from mcp_agent.tracing.token_counter import TokenNode
from mcp_agent.human_input.console_handler import console_input_callback
from mcp_agent.elicitation.handler import console_elicitation_callback
from mcp_agent.mcp.gen_client import gen_client
from mcp_agent.config import MCPServerSettings, Settings, LoggerSettings, MCPSettings, MCPServerAuthSettings, \
    MCPOAuthClientSettings

# Note: This is purely optional:
# if not provided, a default FastMCP server will be created by MCPApp using create_mcp_server_for_app()
mcp = FastMCP(name="basic_agent_server", instructions="My basic agent server example.")


class MCPServerOAuthSettings:
    pass


settings = Settings(
        execution_engine="asyncio",
        logger=LoggerSettings(level="info"),
        mcp=MCPSettings(
            servers={
                "github": MCPServerSettings(
                    name="github",
                    transport="streamable_http",
                    url="https://api.githubcopilot.com/mcp/",
                    auth=MCPServerAuthSettings(
                        oauth=MCPOAuthClientSettings(
                            enabled=True,
                            scopes= [
                                "read:org",  # Required for search_orgs tool
                                "public_repo",  # Access to public repositories
                                "user:email"  # User information access
                            ],
                            authorization_server=AnyHttpUrl("https://github.com/login/oauth"),
                            resource=AnyHttpUrl("https://api.githubcopilot.com/mcp")
                        )
                    )
                )
            }
        ),
    )

# Define the MCPApp instance. The server created for this app will advertise the
# MCP logging capability and forward structured logs upstream to connected clients.
app = MCPApp(
    name="basic_agent_server",
    description="Basic agent server example",
    mcp=mcp,
    settings=settings,
)


@app.tool(name="github_org_search")
async def github_org_search(query: str, app_ctx: Optional[AppContext] = None) -> str:
    from mcp_agent.mcp.gen_client import gen_client

    try:
        async with gen_client(
                "github",
                server_registry=app_ctx.server_registry,
                context=app_ctx
        ) as github_client:
            result = await github_client.call_tool(
                "search_orgs",
                {
                    "query": query,
                    "perPage": 10,
                    "sort": "best-match",
                    "order": "desc"
                }
            )

            organizations = []
            if result.content:
                for content_item in result.content:
                    if hasattr(content_item, 'text'):
                        try:
                            data = json.loads(content_item.text)
                            if isinstance(data, dict) and 'items' in data:
                                organizations.extend(data['items'])
                            elif isinstance(data, list):
                                organizations.extend(data)
                        except json.JSONDecodeError:
                            pass

            return str(organizations)
    except Exception as e:
        import traceback
        return f"Error: {traceback.format_exc()}"

async def main():
    async with app.run() as agent_app:
        # Log registered workflows and agent configurations
        agent_app.logger.info(f"Creating MCP server for {agent_app.name}")

        agent_app.logger.info("Registered workflows:")
        for workflow_id in agent_app.workflows:
            agent_app.logger.info(f"  - {workflow_id}")

        # Create the MCP server that exposes both workflows and agent configurations,
        # optionally using custom FastMCP settings
        mcp_server = create_mcp_server_for_app(agent_app)
        agent_app.logger.info(f"MCP Server settings: {mcp_server.settings}")

        # Run the server
        await mcp_server.run_stdio_async()
        # await mcp_server.run_sse_async()


if __name__ == "__main__":
    asyncio.run(main())
