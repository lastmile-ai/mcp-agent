import asyncio
from temporalio.client import Client
from temporalio.worker import Worker
from basic_workflow import BasicWorkflow
from mcp_agent.temporal import MCPAgentPlugin
from main import app, settings


async def main():
    async with app.run() as running_app:
        # Create plugin with config and context
        plugin = MCPAgentPlugin(
            config=settings.temporal, context=running_app.context, app=app
        )

        client = await Client.connect(
            "localhost:7233",
            plugins=[plugin],
        )

        # Create worker with plugin - activities will be auto-registered
        # The plugin will be applied to both client and worker through the worker
        worker = Worker(client, task_queue="example_queue", workflows=[BasicWorkflow])

        print("Running worker with MCP Agent plugin...")
        print("Task queue: example_queue")
        print(f"Namespace: {settings.temporal.namespace}")

        await worker.run()


if __name__ == "__main__":
    asyncio.run(main())
