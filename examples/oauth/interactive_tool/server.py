"""
Simple MCP server that exposes a GitHub search tool and relies on the OAuth
authorization flow. When the tool is invoked without stored credentials, the
server will issue an auth/request so the client can complete the OAuth login
in a browser and return the authorization code.
"""

from __future__ import annotations

import asyncio
import json
import os
import traceback
from typing import Optional

from pydantic import AnyHttpUrl

from mcp.server.fastmcp import FastMCP

from mcp_agent.app import MCPApp
from mcp_agent.config import (
    LoggerSettings,
    MCPOAuthClientSettings,
    MCPServerAuthSettings,
    MCPServerSettings,
    MCPSettings,
    OAuthSettings,
    OAuthTokenStoreSettings,
    Settings,
)
from mcp_agent.core.context import Context as AppContext
from mcp_agent.mcp.gen_client import gen_client
from mcp_agent.server.app_server import create_mcp_server_for_app

CLIENT_ID = os.getenv("GITHUB_CLIENT_ID")
CLIENT_SECRET = os.getenv("GITHUB_CLIENT_SECRET")

if not CLIENT_ID or not CLIENT_SECRET:
    raise SystemExit(
        "Set GITHUB_CLIENT_ID and GITHUB_CLIENT_SECRET environment variables "
        "with credentials for a GitHub OAuth App before running this example."
    )

# Optional FastMCP instance (MCPApp can construct one automatically,
# but providing it makes the instructions clearer).
mcp = FastMCP(
    name="github_demo",
    instructions="Demo GitHub search tool that requires OAuth authentication.",
)

redis_url = os.getenv("OAUTH_REDIS_URL")
if redis_url:
    token_store = OAuthTokenStoreSettings(
        backend="redis",
        redis_url=redis_url,
    )
else:
    token_store = OAuthTokenStoreSettings()

settings = Settings(
    execution_engine="asyncio",
    logger=LoggerSettings(level="debug"),
    oauth=OAuthSettings(
        callback_base_url=AnyHttpUrl("http://localhost:8000"),
        flow_timeout_seconds=300,
        loopback_ports=[33418],
        token_store=token_store,
    ),
    mcp=MCPSettings(
        servers={
            "github": MCPServerSettings(
                name="github",
                transport="streamable_http",
                url="https://api.githubcopilot.com/mcp/",
                auth=MCPServerAuthSettings(
                    oauth=MCPOAuthClientSettings(
                        enabled=True,
                        client_id=CLIENT_ID,
                        client_secret=CLIENT_SECRET,
                        scopes=[
                            "read:org",
                            "public_repo",
                            "user:email",
                        ],
                        authorization_server=AnyHttpUrl(
                            "https://github.com/login/oauth"
                        ),
                        use_internal_callback=True,
                        include_resource_parameter=False,
                    )
                ),
            )
        }
    ),
)

app = MCPApp(
    name="github_oauth_demo",
    description="Example MCP server that performs GitHub organization searches.",
    mcp=mcp,
    settings=settings,
    session_id="github-oauth-demo",
)


@app.tool(name="github_org_search")
async def github_org_search(query: str, app_ctx: Optional[AppContext] = None) -> str:
    """Search GitHub organizations using the remote MCP server."""
    context = app_ctx or app.context
    async with gen_client(
        "github",
        server_registry=context.server_registry,
        context=context,
    ) as github_client:
        tools = await github_client.list_tools()
        context.logger.info(
            "github_org_search: available tools from GitHub MCP",
            data={"tools": [tool.name for tool in tools.tools]},
        )
        try:
            result = await github_client.call_tool(
                "search_repositories",
                {
                    "query": f"org:{query}",
                    "per_page": 5,
                    "sort": "best-match",
                    "order": "desc",
                },
            )
        except Exception as exc:
            context.logger.error(
                "github_org_search: call to remote GitHub MCP failed",
                exception=repr(exc),
                traceback=traceback.format_exc(),
            )
            raise

        orgs: list[dict] = []
        if result.content:
            for item in result.content:
                text = getattr(item, "text", None)
                if not text:
                    continue
                try:
                    payload = json.loads(text)
                except json.JSONDecodeError:
                    continue
                if isinstance(payload, dict) and "items" in payload:
                    orgs.extend(payload["items"])
                elif isinstance(payload, list):
                    orgs.extend(payload)
        return json.dumps(orgs, indent=2)


async def main() -> None:
    async with app.run() as running_app:
        running_app.logger.info("Starting GitHub OAuth demo server")
        server = create_mcp_server_for_app(running_app)
        await server.run_sse_async()


if __name__ == "__main__":
    asyncio.run(main())
