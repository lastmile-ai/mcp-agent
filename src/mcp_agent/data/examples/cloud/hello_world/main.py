"""
Hello World MCP App Example

This example demonstrates a very basic MCP app that defines two tools using the
`@app.tool` and `@app.async_tool` decorators:

1. hello_world: Uses `@app.tool` decorator to create a tool that returns its result immediately.
2. hello_world_async: Uses `@app.async_tool` decorator to create an asynchronous tool that starts
   a workflow run; the result can be retrieved from the workflow status later.

"""

import asyncio

from mcp_agent.app import MCPApp
from mcp_agent.server.app_server import create_mcp_server_for_app

app = MCPApp(name="hello_world")


@app.tool()
def hello_world() -> str:
    """A simple tool that returns 'Hello, World!'"""
    return "Hello, World!"


@app.async_tool()
async def hello_world_async() -> str:
    """A simple async tool that starts a workflow run that returns 'Hello, World!'"""
    return "Hello, World!"


# NOTE: This main function is useful for local testing but will be ignored in the cloud deployment.
async def main():
    async with app.run() as agent_app:
        mcp_server = create_mcp_server_for_app(agent_app)
        await mcp_server.run_sse_async()


if __name__ == "__main__":
    asyncio.run(main())
