"""
Workflow MCP Server Example

This example demonstrates how to create and run MCP Agent workflows using Temporal:
1. Standard workflow execution with agent-based processing
2. Pause and resume workflow using Temporal signals

The example showcases the durable execution capabilities of Temporal.
"""

import asyncio
import logging
import os

from mcp_agent.app import MCPApp
from mcp_agent.agents.agent import Agent
from mcp_agent.core.context import Context
from mcp_agent.executor.workflow_signal import Signal
from mcp_agent.server.app_server import create_mcp_server_for_app
from mcp_agent.executor.workflow import Workflow, WorkflowResult
from mcp_agent.workflows.llm.augmented_llm_openai import OpenAIAugmentedLLM

# Initialize logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Create a single FastMCPApp instance (which extends MCPApp)
app = MCPApp(name="basic_agent_server", description="Basic agent server example")


@app.workflow
class BasicAgentWorkflow(Workflow[str]):
    """
    A basic workflow that demonstrates how to create a simple agent.
    This workflow processes input using an agent with access to fetch and filesystem.
    """

    @app.workflow_run
    async def run(
        self, input: str = "What is the Model Context Protocol?"
    ) -> WorkflowResult[str]:
        """
        Run the basic agent workflow.

        Args:
            input: The input string to prompt the agent.

        Returns:
            WorkflowResult containing the processed data.
        """
        print(f"Running BasicAgentWorkflow with input: {input}")

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
            print(f"Agent result: {result}")
            return WorkflowResult(value=result)


@app.tool
async def finder_tool(request: str, app_ctx: Context | None = None) -> str:
    """
    Run the basic agent workflow using the app.tool decorator to set up the workflow.
    The code in this function is run in workflow context.
    LLM calls are executed in the activity context.
    You can use the app_ctx to access the executor to run activities explicitly.
    Functions decorated with @app.workflow_task will be run in activity context.

    Args:
        input: The input string to prompt the agent.

    Returns:
        The result of the agent call. This tool will be run syncronously and block until workflow completion.
        To create this as an async tool, use @app.async_tool instead, which will return the workflow ID and run ID.
    """

    app = app_ctx.app

    logger = app.logger
    logger.info(f"Running finder_tool with input: {request}")

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
            message=request,
        )
        logger.info(f"Agent result: {result}")

    return result


@app.workflow
class PauseResumeWorkflow(Workflow[str]):
    """
    A workflow that demonstrates Temporal's signaling capabilities.
    This workflow pauses execution and waits for a signal before continuing.
    """

    @app.workflow_run
    async def run(
        self, message: str = "This workflow demonstrates pause and resume functionality"
    ) -> WorkflowResult[str]:
        """
        Run the pause-resume workflow.

        Args:
            message: A message to include in the workflow result.

        Returns:
            WorkflowResult containing the processed data.
        """
        print(f"Starting PauseResumeWorkflow with message: {message}")
        print(f"Workflow is pausing, workflow_id: {self.id}, run_id: {self.run_id}")
        print(
            "To resume this workflow, use the 'workflows-resume' tool or the Temporal UI"
        )

        # Wait for the resume signal - this will pause the workflow until the signal is received
        await app.context.executor.signal_bus.wait_for_signal(
            Signal(name="resume", workflow_id=self.id, run_id=self.run_id),
        )

        print("Signal received, workflow is resuming...")
        result = f"Workflow successfully resumed! Original message: {message}"
        print(f"Final result: {result}")
        return WorkflowResult(value=result)


async def main():
    async with app.run() as agent_app:
        # Log registered workflows and agent configurations
        logger.info(f"Creating MCP server for {agent_app.name}")

        logger.info("Registered workflows:")
        for workflow_id in agent_app.workflows:
            logger.info(f"  - {workflow_id}")
        # Create the MCP server that exposes both workflows and agent configurations
        mcp_server = create_mcp_server_for_app(agent_app)

        # Run the server
        await mcp_server.run_sse_async()


if __name__ == "__main__":
    asyncio.run(main())
