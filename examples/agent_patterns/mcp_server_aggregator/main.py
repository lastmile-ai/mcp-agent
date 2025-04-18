import asyncio
from pathlib import Path

from mcp_agent.app import MCPApp
from mcp_agent.logging.logger import get_logger
from mcp_agent.mcp.mcp_aggregator import MCPAggregator
from rich import print

app = MCPApp(name="mcp_server_aggregator")


async def example_usage_persistent():
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
        result = await aggregator.list_tools()
        logger.info("Tools available:", data=result)

        # Call read_file on the aggregator, which will search all servers for the tool
        result = await aggregator.call_tool(
            name="read_file",
            arguments={"path": str(Path.cwd() / "README.md")},
        )
        logger.info("read_file result:", data=result)

        # Call fetch.fetch on the aggregator
        # (i.e. server-namespacing -- fetch is the servername, which exposes fetch tool)
        result = await aggregator.call_tool(
            name="fetch_fetch",
            arguments={"url": "https://jsonplaceholder.typicode.com/todos/1"},
        )
        logger.info("fetch result:", data=result)
    except Exception as e:
        logger.error("Error in example_usage_persistent:", data=e)
    finally:
        logger.info("Closing all server connections on aggregator...")
        await aggregator.close()


async def example_usage():
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
        result = await aggregator.list_tools()
        logger.info("Tools available:", data=result)

        # Call read_file on the aggregator, which will search all servers for the tool
        result = await aggregator.call_tool(
            name="read_file",
            arguments={"path": str(Path.cwd() / "README.md")},
        )
        logger.info("read_file result:", data=result)

        # Call fetch.fetch on the aggregator
        # (i.e. server-namespacing -- fetch is the servername, which exposes fetch tool)
        result = await aggregator.call_tool(
            name="fetch_fetch",
            arguments={"url": "https://jsonplaceholder.typicode.com/todos/1"},
        )
        logger.info(f"fetch result: {str(result)}")
    except Exception as e:
        logger.error("Error in example_usage:", data=e)
    finally:
        logger.info("Closing all server connections on aggregator...")
        await aggregator.close()


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
