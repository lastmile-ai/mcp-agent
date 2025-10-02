import asyncio
from pathlib import Path

from mcp_agent.app import MCPApp
from mcp_agent.logging.logger import get_logger
from mcp_agent.mcp.mcp_aggregator import MCPAggregator
from rich import print

app = MCPApp(name="mcp_server_aggregator")


@app.tool
async def example_usage_persistent() -> str:
    """
    this example function/tool call will use an MCP aggregator
    to connect to both the file and filesystem servers and
    aggregate them together, so you can list all tool calls from
    both servers at once. The connections to the servers will
    be persistent.
    """
    result = ""
    context = app.context

    logger = get_logger("mcp_server_aggregator.example_usage_persistent")
    logger.info("Hello, world! Let's create an MCP aggregator (server-of-servers)...")
    logger.info("Current config:", data=context.config)

    # Create an MCP aggregator that connects to the fetch and filesystem servers
    aggregator = None

    try:
        aggregator = await MCPAggregator.create(
            server_names=["fetch", "filesystem"],
            connection_persistence=True,  # By default connections are torn down after each call
        )
        # Call list_tools on the aggregator, which will search all servers for the tool
        logger.info("Aggregator: Calling list_tools...")
        output = await aggregator.list_tools()
        logger.info("Tools available:", data=output)
        result += "Tools available:" + str(output)

        # Call read_file on the aggregator, which will search all servers for the tool
        output = await aggregator.call_tool(
            name="read_text_file",
            arguments={"path": str(Path.cwd() / "README.md")},
        )
        logger.info("read_text_file result:", data=output)
        result += "\n\nread_text_file result:" + str(output)

        # Call fetch.fetch on the aggregator
        # (i.e. server-namespacing -- fetch is the servername, which exposes fetch tool)
        output = await aggregator.call_tool(
            name="fetch_fetch",
            arguments={"url": "https://jsonplaceholder.typicode.com/todos/1"},
        )
        logger.info("fetch result:", data=output)
        result += f"\n\nfetch result: {str(output)}"
    except Exception as e:
        logger.error("Error in example_usage_persistent:", data=e)
    finally:
        logger.info("Closing all server connections on aggregator...")
        await aggregator.close()

    return result


@app.tool
async def example_usage() -> str:
    """
    this example function/tool call will use an MCP aggregator
    to connect to both the file and filesystem servers and
    aggregate them together, so you can list all tool calls from
    both servers at once.
    """
    result = ""
    logger = get_logger("mcp_server_aggregator.example_usage")

    context = app.context
    logger.info("Hello, world! Let's create an MCP aggregator (server-of-servers)...")
    logger.info("Current config:", data=context.config)

    # Create an MCP aggregator that connects to the fetch and filesystem servers
    aggregator = None

    try:
        aggregator = await MCPAggregator.create(
            server_names=["fetch", "filesystem"],
            connection_persistence=False,
        )
        # Call list_tools on the aggregator, which will search all servers for the tool
        logger.info("Aggregator: Calling list_tools...")
        output = await aggregator.list_tools()
        logger.info("Tools available:", data=output)
        result += "Tools available:" + str(output)

        # Call read_file on the aggregator, which will search all servers for the tool
        output = await aggregator.call_tool(
            name="read_text_file",
            arguments={"path": str(Path.cwd() / "README.md")},
        )
        logger.info("read_text_file result:", data=output)
        result += "\n\nread_text_file result:" + str(output)

        # Call fetch.fetch on the aggregator
        # (i.e. server-namespacing -- fetch is the servername, which exposes fetch tool)
        output = await aggregator.call_tool(
            name="fetch_fetch",
            arguments={"url": "https://jsonplaceholder.typicode.com/todos/1"},
        )
        logger.info(f"fetch result: {str(output)}")
        result += f"\n\nfetch result: {str(output)}"
    except Exception as e:
        logger.error("Error in example_usage:", data=e)
    finally:
        logger.info("Closing all server connections on aggregator...")
        await aggregator.close()

    print(result)

    return result


if __name__ == "__main__":
    import time

    async def main():
        try:
            await app.initialize()

            start = time.time()
            await example_usage_persistent()
            end = time.time()
            persistent_time = end - start

            start = time.time()
            await example_usage()
            end = time.time()
            non_persistent_time = end - start

            print(f"\nPersistent connection time: {persistent_time:.2f}s")
            print(f"\nNon-persistent connection time: {non_persistent_time:.2f}s")
        finally:
            await app.cleanup()

    asyncio.run(main())
