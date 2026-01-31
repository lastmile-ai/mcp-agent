"""
MCP Agent MCP Tools OAuth Example

This example demonstrates how to integrate OAuth 2.0-enabled MCP servers within mcp-agent.

1. Interactive (lazy) authorization: When the tool is invoked without a cached token, the server issues an `auth/request` message and the client opens the browser so you can complete the GitHub sign-in.

2. Pre-authorized workflows: Leverage the workflows-store-credentials mcp-agent tool to cache a token for a specified workflow before the workflow is run. Once the token is saved, the workflow can access the downstream MCP server without further user interaction.

"""

import asyncio
import json
from typing import Optional

from mcp_agent.app import MCPApp
from mcp_agent.core.context import Context as AppContext
from mcp_agent.mcp.gen_client import gen_client
from mcp_agent.server.app_server import create_mcp_server_for_app

app = MCPApp(
    name="oauth_mcp_tools",
    description="Example of MCP tools with OAuth integration",
)

# You can pre-authorize this workflow by calling workflows-store-credentials tool with:
# {
#   "workflow_name": "github_org_search_activity",
#   "tokens": [
#     {
#         "access_token": access_token,
#         "server_name": "github",
#     }
#   ]
# }


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
    context = app_ctx or app.context
    result = await app.executor.execute(github_org_search_activity, query)
    context.logger.info("Workflow result", data={"result": result})

    return result


# NOTE: This main function is useful for local testing but will be ignored in the cloud deployment.
async def main():
    async with app.run() as agent_app:
        mcp_server = create_mcp_server_for_app(agent_app)
        await mcp_server.run_sse_async()


if __name__ == "__main__":
    asyncio.run(main())
