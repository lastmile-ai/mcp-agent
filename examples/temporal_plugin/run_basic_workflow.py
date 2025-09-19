import asyncio
from basic_workflow import BasicWorkflow
from mcp_agent.temporal import MCPAgentPlugin
from temporalio.client import Client
from uuid import uuid4


async def main():
    # Create client connected to server at the given address
    client = await Client.connect(
        "localhost:7233",
        plugins=[
            MCPAgentPlugin(),
        ],
    )

    # Execute a workflow

    result = await client.execute_workflow(
        BasicWorkflow.run,
        "Tell me about recursion in programming.",
        id=str(uuid4()),
        task_queue="example_queue",
    )
    print(f"Result: {result}")


if __name__ == "__main__":
    asyncio.run(main())
