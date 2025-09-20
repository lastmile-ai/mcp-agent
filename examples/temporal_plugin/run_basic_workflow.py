import asyncio
from datetime import timedelta
from basic_workflow import BasicWorkflow
from mcp_agent.temporal import MCPAgentPlugin
from temporalio.client import Client
from uuid import uuid4
from main import settings, app


async def main():
    async with app.run() as running_app:
        # Create plugin with config (no context needed for client-only usage)
        plugin = MCPAgentPlugin(
            config=settings.temporal, context=running_app.context, app=app
        )

        # Create client connected to server at the given address
        client = await Client.connect(
            "localhost:7233",
            plugins=[plugin],
        )

        # Execute a workflow
        workflow_id = f"basic-workflow-{uuid4()}"
        print(f"Starting workflow with ID: {workflow_id}")
        print("Task queue: mcp-agent")

        result = await client.execute_workflow(
            BasicWorkflow.run,
            "Print the first 2 paragraphs of https://modelcontextprotocol.io/introduction",
            id=workflow_id,
            task_queue="mcp-agent",
            task_timeout=timedelta(minutes=10),
            execution_timeout=timedelta(minutes=10),
            run_timeout=timedelta(minutes=10),
        )
        print(f"Result: {result}")


if __name__ == "__main__":
    asyncio.run(main())
