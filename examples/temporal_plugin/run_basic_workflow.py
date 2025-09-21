import asyncio
from basic_workflow import BasicWorkflow
from mcp_agent.temporal import MCPAgentPlugin
from temporalio.client import Client
from uuid import uuid4
from main import app


async def main():
    async with app.run() as running_app:
        plugin = MCPAgentPlugin(running_app)

        # Create client connected to server at the given address
        client = await Client.connect(
            running_app.config.temporal.host,
            plugins=[plugin],
        )

        # Execute a workflow
        workflow_id = f"basic-workflow-{uuid4()}"
        task_queue = running_app.config.temporal.task_queue
        print(f"Starting workflow with ID: {workflow_id}")
        print(f"Task queue: {task_queue}")

        result = await client.execute_workflow(
            BasicWorkflow.run,
            "Print the first 2 paragraphs of https://modelcontextprotocol.io/introduction",
            id=workflow_id,
            task_queue=task_queue,
        )
        print(f"Result: {result}")


if __name__ == "__main__":
    asyncio.run(main())
