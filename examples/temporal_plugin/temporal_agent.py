import asyncio
from uuid import uuid4
from temporalio import workflow
from mcp_agent.workflows.llm.augmented_llm_openai import OpenAIAugmentedLLM
from mcp_agent.agents.agent import Agent
from temporalio.client import Client
from mcp_agent.temporal import MCPAgentPlugin
from mcp_agent.app import MCPApp
from temporalio.worker import Worker


@workflow.defn
class BasicWorkflow:
    @workflow.run
    async def run(self, prompt: str) -> str:
        simple_agent = Agent(
            name="finder",
            instruction="You are a helpful agent",
            server_names=["fetch"],
        )

        async with simple_agent:
            llm = await simple_agent.attach_llm(OpenAIAugmentedLLM)
            result = await llm.generate_str(prompt)
            return result


async def main():
    app = MCPApp(name="mcp_basic_agent")

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
            output = await client.execute_workflow(
                BasicWorkflow.run,
                args=[
                    "Print the first 2 paragraphs of https://modelcontextprotocol.io/introduction"
                ],
                id=f"basic-workflow-{uuid4()}",
                task_queue=running_app.config.temporal.task_queue,
            )
            print(output)


if __name__ == "__main__":
    asyncio.run(main())
