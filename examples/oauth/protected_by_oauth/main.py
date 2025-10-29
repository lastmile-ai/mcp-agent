"""
Demonstration of an MCP agent server configured with OAuth.
"""

import asyncio
from typing import Optional
from pydantic import AnyHttpUrl

from mcp_agent.core.context import Context as AppContext

from mcp_agent.app import MCPApp
from mcp_agent.server.app_server import create_mcp_server_for_app
from mcp_agent.config import (
    Settings,
    LoggerSettings,
    OAuthTokenStoreSettings,
    OAuthSettings,
    MCPAuthorizationServerSettings,
)


auth_server = "https://auth.mcp-agent.com"  # the MCP Agent Cloud auth server, or replace with your own
resource_server = "http://localhost:8000"  # This server's URL

client_id = "<client id from registration.py>"
client_secret = "<client secret from registration.py>"

settings = Settings(
    execution_engine="asyncio",
    logger=LoggerSettings(level="info"),
    authorization=MCPAuthorizationServerSettings(
        enabled=True,
        issuer_url=AnyHttpUrl(auth_server),
        resource_server_url=AnyHttpUrl(resource_server),
        client_id=client_id,
        client_secret=client_secret,
        required_scopes=["mcp"],
        expected_audiences=[client_id],
    ),
    oauth=OAuthSettings(
        callback_base_url=AnyHttpUrl(resource_server),
        flow_timeout_seconds=300,
        token_store=OAuthTokenStoreSettings(refresh_leeway_seconds=60),
    ),
)


# Define the MCPApp instance. The server created for this app will advertise the
# MCP logging capability and forward structured logs upstream to connected clients.
app = MCPApp(
    name="oauth_demo",
    description="Basic agent server example",
    settings=settings,
)


@app.tool(name="hello_world")
async def hello(app_ctx: Optional[AppContext] = None) -> str:
    # Use the context's app if available for proper logging with upstream_session
    _app = app_ctx.app if app_ctx else app
    # Ensure the app's logger is bound to the current context with upstream_session
    if _app._logger and hasattr(_app._logger, "_bound_context"):
        _app._logger._bound_context = app_ctx

    if app_ctx.current_user:
        user = app_ctx.current_user
        if user.claims and "username" in user.claims:
            return f"Hello, {user.claims['username']}!"
        else:
            return f"Hello, user with ID {user.subject}!"
    else:
        return "Hello, anonymous user!"


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
