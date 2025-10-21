import asyncio
import inspect
import json
import os
from pathlib import Path
from typing import Optional

from mcp.server.fastmcp import FastMCP

from mcp_agent.app import MCPApp
from mcp_agent.config import get_settings, OAuthTokenStoreSettings, OAuthSettings
from mcp_agent.core.context import Context as AppContext
from mcp_agent.mcp.gen_client import gen_client
from mcp_agent.server.app_server import create_mcp_server_for_app


mcp = FastMCP(
    name="pre_authorize_server",
    instructions="Pre-authorize workflow example server.",
)


def _load_settings():
    signature = inspect.signature(get_settings)
    kwargs = {}
    config_path = Path(__file__).with_name("mcp_agent.config.yaml")
    if "config_path" in signature.parameters:
        kwargs["config_path"] = str(config_path)
    if "set_global" in signature.parameters:
        kwargs["set_global"] = False
    return get_settings(**kwargs)


settings = _load_settings()

redis_url = os.getenv("OAUTH_REDIS_URL")
if redis_url:
    settings.oauth = settings.oauth or OAuthSettings()
    settings.oauth.token_store = OAuthTokenStoreSettings(
        backend="redis",
        redis_url=redis_url,
    )
elif not getattr(settings.oauth, "token_store", None):
    settings.oauth = settings.oauth or OAuthSettings()
    settings.oauth.token_store = OAuthTokenStoreSettings()

github_settings = (
    settings.mcp.servers.get("github")
    if settings.mcp and settings.mcp.servers
    else None
)
github_oauth = (
    github_settings.auth.oauth
    if github_settings and github_settings.auth and github_settings.auth.oauth
    else None
)

if not github_oauth or not github_oauth.client_id or not github_oauth.client_secret:
    raise SystemExit(
        "GitHub OAuth client_id/client_secret must be provided via mcp_agent.config.yaml or mcp_agent.secrets.yaml."
    )

app = MCPApp(
    name="pre_authorize_server",
    description="Pre-authorize workflow example",
    mcp=mcp,
    settings=settings,
    session_id="workflow-pre-authorize",
)


@app.workflow_task(name="github_org_search_activity")
async def github_org_search_activity(query: str) -> str:
    app.logger.info("github_org_search_activity started")
    try:
        async with gen_client(
            "github", server_registry=app.context.server_registry, context=app.context
        ) as github_client:
            app.logger.info("Obtained GitHub MCP client")
            result = await github_client.call_tool(
                "search_repositories",
                {
                    "query": f"org:{query}",
                    "per_page": 5,
                    "sort": "best-match",
                    "order": "desc",
                },
            )

            repositories = []
            if result.content:
                for content_item in result.content:
                    if hasattr(content_item, "text"):
                        try:
                            data = json.loads(content_item.text)
                            if isinstance(data, dict) and "items" in data:
                                repositories.extend(data["items"])
                            elif isinstance(data, list):
                                repositories.extend(data)
                        except json.JSONDecodeError:
                            pass

            app.logger.info("Repositories fetched", data={"count": len(repositories)})
            return json.dumps(repositories, indent=2)
    except Exception as e:
        import traceback

        traceback.print_exc()
        return f"Error: {e}"


@app.tool(name="github_org_search")
async def github_org_search(query: str, app_ctx: Optional[AppContext] = None) -> str:
    if app._logger and hasattr(app._logger, "_bound_context"):
        app._logger._bound_context = app.context

    result = await app.executor.execute(github_org_search_activity, query)
    app.logger.info("Workflow result", data={"result": result})

    return result


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
        # await mcp_server.run_stdio_async()
        await mcp_server.run_sse_async()


if __name__ == "__main__":
    asyncio.run(main())
