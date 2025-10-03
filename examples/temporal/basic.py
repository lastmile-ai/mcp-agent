"""
Example of using Temporal as the execution engine for MCP Agent workflows.
This example demonstrates how to create a workflow using the app.workflow and app.workflow_run
decorators, and how to run it using the Temporal executor.
"""

import asyncio
import logging
import os

from mcp_agent.agents.agent import Agent
from mcp_agent.executor.temporal import TemporalExecutor
from mcp_agent.executor.workflow import Workflow, WorkflowResult
from mcp_agent.workflows.llm.augmented_llm_openai import OpenAIAugmentedLLM

from main import app

# Initialize logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@app.workflow
class SimpleWorkflow(Workflow[str]):
    """
    A simple workflow that demonstrates the basic structure of a Temporal workflow.
    """

    @app.workflow_run
    async def run(self, input: str) -> WorkflowResult[str]:
        """
        Run the workflow, processing the input data.

        Args:
            input_data: The data to process

        Returns:
            A WorkflowResult containing the processed data
        """
        finder_agent = Agent(
            name="finder",
            instruction="""You are a helpful assistant.""",
            server_names=["fetch", "filesystem"],
        )

        context = app.context
        context.config.mcp.servers["filesystem"].args.extend([os.getcwd()])

        async with finder_agent:
            finder_llm = await finder_agent.attach_llm(OpenAIAugmentedLLM)

            result = await finder_llm.generate_str(
                message=input,
            )
            return WorkflowResult(value=result)


async def main():
    async with app.run() as agent_app:
        executor: TemporalExecutor = agent_app.executor
        handle = await executor.start_workflow(
            "SimpleWorkflow",
            "Print the first 2 paragraphs of https://modelcontextprotocol.io/introduction",
        )
        a = await handle.result()
        print(a)


if __name__ == "__main__":
    asyncio.run(main())
