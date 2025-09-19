import asyncio
from temporalio.client import Client
from temporalio.worker import Worker
from basic_workflow import BasicWorkflow
from mcp_agent.temporal import MCPAgentPlugin


async def main():
    client = await Client.connect(
        "localhost:7233",
        plugins=[MCPAgentPlugin()],
    )

    worker = Worker(client, task_queue="example_queue", workflows=[BasicWorkflow])
    print("Running worker...")
    await worker.run()


if __name__ == "__main__":
    asyncio.run(main())
