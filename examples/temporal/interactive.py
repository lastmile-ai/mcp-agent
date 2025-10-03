"""
Example of using Temporal as the execution engine for MCP Agent workflows.
This example demonstrates how to include human interaction through the
InteractiveWorkflow class, allowing the workflow to pause and wait for user input.

When running this workflow, it will pause for human input. From the temporal UI,
you can inspect the requested information by going to the "Queries" tab
and executing the `get_human_input_request` query to see the requested information.
The response can be provided by sending a signal of type "provide_human_input",
with a message body like '{"response": "Your input here"}'
"""

import asyncio
import logging

from mcp_agent.agents.agent import Agent
from mcp_agent.executor.temporal import TemporalExecutor
from mcp_agent.executor.temporal.interactive_workflow import InteractiveWorkflow
from mcp_agent.executor.workflow import WorkflowResult
from mcp_agent.workflows.llm.augmented_llm_openai import OpenAIAugmentedLLM

from main import app

# Initialize logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@app.workflow
class WorkflowWithInteraction(InteractiveWorkflow[str]):
    """
    A simple workflow that demonstrates the human interaction in a temporal workflow.
    """

    @app.workflow_run
    async def run(self, input: str) -> WorkflowResult[str]:
        """
        Run the workflow, processing the input data.

        Args:
            input: The data to process

        Returns:
            A WorkflowResult containing the processed data
        """
        poet = Agent(
            name="poet",
            instruction="""You are a helpful assistant.""",
            human_input_callback=self.create_input_callback(),
        )

        async with poet:
            finder_llm = await poet.attach_llm(OpenAIAugmentedLLM)

            result = await finder_llm.generate_str(
                message=input,
            )
            return WorkflowResult(value=result)


async def main():
    async with app.run() as agent_app:
        executor: TemporalExecutor = agent_app.executor
        handle = await executor.start_workflow(
            "WorkflowWithInteraction",
            "Ask the user for a subject, then generate a poem about it.",
        )
        a = await handle.result()
        print(a)


if __name__ == "__main__":
    asyncio.run(main())
