"""
Workflow MCP Server Example

This example demonstrates three approaches to creating agents and workflows:
1. Traditional workflow-based approach with manual agent creation
2. Programmatic agent configuration using AgentConfig
3. Declarative agent configuration using FastMCPApp decorators
"""

import asyncio
import json
import os
from pydantic import AnyHttpUrl

from mcp.server.fastmcp import FastMCP

from mcp_agent.app import MCPApp
from mcp_agent.server.app_server import create_mcp_server_for_app

from mcp_agent.config import MCPServerSettings, Settings, LoggerSettings, MCPSettings, MCPServerAuthSettings, \
    MCPOAuthClientSettings, OAuthSettings, OAuthTokenStoreSettings, TemporalSettings

# Note: This is purely optional:
# if not provided, a default FastMCP server will be created by MCPApp using create_mcp_server_for_app()
mcp = FastMCP(name="basic_agent_server", instructions="My basic agent server example.")

client_id = os.getenv('GITHUB_CLIENT_ID')

settings = Settings(
        execution_engine="temporal",
        temporal=TemporalSettings(
            host="localhost:7233",
            namespace="default",
            task_queue="mcp-agent",
            max_concurrent_activities=10,
        ),
        logger=LoggerSettings(level="info"),
        oauth=OAuthSettings(
            callback_base_url=AnyHttpUrl("http://localhost:8080"),
            flow_timeout_seconds=300,
            token_store=OAuthTokenStoreSettings(refresh_leeway_seconds=60),
        ),
        mcp=MCPSettings(
            servers={
                "github": MCPServerSettings(
                    name="github",
                    transport="streamable_http",
                    url="https://api.githubcopilot.com/mcp/",
                    auth=MCPServerAuthSettings(
                        oauth=MCPOAuthClientSettings(
                            client_id=client_id,
                            use_internal_callback=True,
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


@app.workflow_task(name="github_org_search_activity")
async def github_org_search_activity(query: str) -> str:
    from mcp_agent.mcp.gen_client import gen_client

    print("running activity)")
    try:
        async with gen_client(
                "github",
                server_registry=app.context.server_registry,
                context=app.context
        ) as github_client:
            print("got client")
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

            print(f"Organizations: {organizations}")
            return str(organizations)
    except Exception as e:
        import traceback
        traceback.print_exc()
        return f"Error: {e}"

@app.tool(name="github_org_search")
async def github_org_search(query: str) -> str:
    if app._logger and hasattr(app._logger, "_bound_context"):
        app._logger._bound_context = app.context
    logger = app.logger

    result = await app.executor.execute(github_org_search_activity, query)
    print(f"Result: {result}, {type(result)}")

    return "ok!"
    # try:
    #     return await app.executor.execute(github_org_search_activity, query)
    # except Exception as e:
    #     import traceback
    #     traceback.print_exc()
    #     return f"Error: {e}"

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
        await mcp_server.run_sse_async()


if __name__ == "__main__":
    asyncio.run(main())
