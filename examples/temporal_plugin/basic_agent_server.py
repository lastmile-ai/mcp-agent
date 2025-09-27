import asyncio
from temporalio.client import Client
from mcp_agent.executor.temporal.plugin import MCPAgentPlugin
from mcp_agent.app import MCPApp
from temporalio.worker import Worker
from basic_workflow import BasicWorkflow
from mcp_agent.server.app_server import create_mcp_server_for_app

app = MCPApp(name="mcp_agent_server")


async def main():
    async with app.run() as running_app:
        plugin = MCPAgentPlugin(running_app)

        client = await Client.connect(
            running_app.config.temporal.host,
            plugins=[plugin],
        )

        async with Worker(
            client,
            task_queue=running_app.config.temporal.task_queue,
            workflows=[BasicWorkflow],
        ):
            print("Registered workflows:")
            for workflow_id in running_app.workflows:
                print(f"  - {workflow_id}")

            mcp_server = create_mcp_server_for_app(running_app)
            await mcp_server.run_sse_async()


if __name__ == "__main__":
    asyncio.run(main())
