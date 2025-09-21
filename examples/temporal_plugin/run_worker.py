import asyncio
from temporalio.client import Client
from temporalio.worker import Worker
from basic_workflow import BasicWorkflow
from mcp_agent.temporal import MCPAgentPlugin
from main import app


async def main():
    async with app.run() as running_app:
        plugin = MCPAgentPlugin(running_app)

        # The plugin will be applied to both client and worker through the client
        client = await Client.connect(
            running_app.config.temporal.host,
            plugins=[plugin],
        )

        worker = Worker(
            client,
            task_queue=running_app.config.temporal.task_queue,
            workflows=[BasicWorkflow],
        )

        print("Running worker with mcp-agent plugin...")
        print(f"Task queue: {running_app.config.temporal.task_queue}")
        print(f"Namespace: {running_app.config.temporal.namespace}")

        await worker.run()


if __name__ == "__main__":
    asyncio.run(main())
