"""
MCP Agent Server OAuth Example

This example demonstrates how to secure an MCP Agent server using OAuth 2.0.
"""

import asyncio
from typing import Optional

from mcp_agent.core.context import Context as AppContext

from mcp_agent.app import MCPApp
from mcp_agent.server.app_server import create_mcp_server_for_app


# Define the MCPApp instance. The server created for this app will advertise the
# MCP logging capability and forward structured logs upstream to connected clients.
app = MCPApp(
    name="oauth_demo",
    description="Basic agent server example",
)


@app.tool(name="hello_world")
async def hello(app_ctx: Optional[AppContext] = None) -> str:
    context = app_ctx or app.context

    if context.current_user:
        user = context.current_user
        if user.claims and "username" in user.claims:
            return f"Hello, {user.claims['username']}!"
        else:
            return f"Hello, user with ID {user.subject}!"
    else:
        return "Hello, anonymous user!"


# NOTE: This main function is useful for local testing but will be ignored in the cloud deployment.
async def main():
    async with app.run() as agent_app:
        mcp_server = create_mcp_server_for_app(agent_app)
        await mcp_server.run_sse_async()


if __name__ == "__main__":
    asyncio.run(main())
