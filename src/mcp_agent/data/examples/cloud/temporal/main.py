"""
Temporal Workflow MCP Server Example

This example demonstrates how to create and run MCP Agent workflows using Temporal:
1. Standard workflow execution with agent-based processing
2. Pause and resume workflow using Temporal signals

The example showcases the durable execution capabilities of Temporal.
"""

import asyncio
import os

from mcp.types import Icon, ModelHint, ModelPreferences, SamplingMessage, TextContent
from temporalio.exceptions import ApplicationError

from mcp_agent.agents.agent import Agent
from mcp_agent.app import MCPApp
from mcp_agent.core.context import Context
from mcp_agent.executor.workflow import Workflow, WorkflowResult
from mcp_agent.server.app_server import create_mcp_server_for_app
from mcp_agent.workflows.llm.augmented_llm_openai import OpenAIAugmentedLLM

app = MCPApp(
    name="basic_agent_server",
    description="Basic agent server example",
)


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

        # Use of the app.logger will forward logs back to the mcp client
        logger = app.logger

        logger.info("[workflow-mode] Starting finder agent in BasicAgentWorkflow.run")
        async with finder_agent:
            finder_llm = await finder_agent.attach_llm(OpenAIAugmentedLLM)

            result = await finder_llm.generate_str(
                message=input,
            )

            # forwards the log to the caller
            logger.info(f"[workflow-mode] Finder agent completed with result {result}")
            # print to the console (for when running locally)
            print(f"Agent result: {result}")
            return WorkflowResult(value=result)


@app.tool(
    name="finder_tool",
    title="Finder Tool",
    description="Run the Finder workflow synchronously.",
    annotations={"idempotentHint": False},
    icons=[Icon(src="emoji:mag")],
    meta={"category": "demo", "engine": "temporal"},
    structured_output=False,
)
async def finder_tool(
    request: str,
    app_ctx: Context | None = None,
) -> str:
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

    context = app_ctx or app.context
    logger = context.logger
    logger.info("[workflow-mode] Running finder_tool", data={"input": request})

    finder_agent = Agent(
        name="finder",
        instruction="""You are a helpful assistant.""",
        server_names=["fetch", "filesystem"],
    )

    context.config.mcp.servers["filesystem"].args.extend([os.getcwd()])

    async with finder_agent:
        finder_llm = await finder_agent.attach_llm(OpenAIAugmentedLLM)

        await context.report_progress(0.4, total=1.0, message="Invoking finder agent")
        result = await finder_llm.generate_str(
            message=request,
        )
        logger.info("[workflow-mode] finder_tool agent result", data={"result": result})
        await context.report_progress(1.0, total=1.0, message="Finder completed")

    return result


@app.workflow
class PauseResumeWorkflow(Workflow[str]):
    """
    A workflow that demonstrates Temporal's signaling capabilities.
    This workflow pauses execution and waits for a signal before continuing.
    """

    @app.workflow_run
    async def run(
        self, input: str = "This workflow demonstrates pause and resume functionality"
    ) -> WorkflowResult[str]:
        """
        Run the pause-resume workflow.

        Args:
            message: A message to include in the workflow result.

        Returns:
            WorkflowResult containing the processed data.
        """
        print(f"Starting PauseResumeWorkflow with message: {input}")
        print(f"Workflow is pausing, workflow_id: {self.id}, run_id: {self.run_id}")
        print(
            "To resume this workflow, use the 'workflows-resume' tool or the Temporal UI"
        )

        # Wait for the resume signal - this will pause the workflow until the signal is received
        timeout_seconds = 60
        try:
            await app.context.executor.wait_for_signal(
                signal_name="resume",
                workflow_id=self.id,
                run_id=self.run_id,
                timeout_seconds=timeout_seconds,
            )
        except TimeoutError as e:
            # Raise ApplicationError to fail the entire workflow run, not just the task
            raise ApplicationError(
                f"Workflow timed out waiting for resume signal after {timeout_seconds} seconds",
                type="SignalTimeout",
                non_retryable=True,
            ) from e

        print("Signal received, workflow is resuming...")
        result = f"Workflow successfully resumed! Original message: {input}"
        print(f"Final result: {result}")
        return WorkflowResult(value=result)


@app.workflow
class SamplingWorkflow(Workflow[str]):
    """Temporal workflow that triggers an MCP sampling request via a nested server."""

    @app.workflow_run
    async def run(self, input: str = "space exploration") -> WorkflowResult[str]:
        app.logger.info(
            "[workflow-mode] SamplingWorkflow starting",
            data={"note": "direct sampling via SessionProxy, then activity sampling"},
        )
        # Direct workflow sampling via SessionProxy (will schedule mcp_relay_request activity)
        app.logger.info(
            "[workflow-mode] SessionProxy.create_message (direct)",
            data={"path": "mcp_relay_request activity"},
        )

        try:
            direct = await app.context.upstream_session.create_message(
                messages=[
                    SamplingMessage(
                        role="user",
                        content=TextContent(
                            type="text", text=f"Write a haiku about {input}."
                        ),
                    )
                ],
                system_prompt="You are a poet.",
                max_tokens=80,
                model_preferences=ModelPreferences(
                    hints=[ModelHint(name="gpt-4o-mini")],
                    costPriority=0.1,
                    speedPriority=0.8,
                    intelligencePriority=0.1,
                ),
            )
            try:
                res = (
                    direct.content.text
                    if isinstance(direct.content, TextContent)
                    else ""
                )
            except Exception:
                res = ""
        except Exception as e:
            app.logger.error(
                "[workflow-mode] Direct sampling failed",
                data={"error": str(e)},
            )
            raise
        app.logger.info(
            "[workflow-mode] Direct sampling result",
            data={"text": res},
        )

        return WorkflowResult(value=res)


@app.workflow
class ElicitationWorkflow(Workflow[str]):
    """Temporal workflow that triggers elicitation via direct session and nested server."""

    @app.workflow_run
    async def run(self, input: str = "proceed") -> WorkflowResult[str]:
        app.logger.info(
            "[workflow-mode] ElicitationWorkflow starting",
            data={"note": "direct elicit via SessionProxy, then activity elicitation"},
        )

        # Direct elicitation via SessionProxy (schedules mcp_relay_request)
        schema = {
            "type": "object",
            "properties": {"confirm": {"type": "boolean"}},
            "required": ["confirm"],
        }
        app.logger.info(
            "[workflow-mode] SessionProxy.elicit (direct)",
            data={"path": "mcp_relay_request activity"},
        )
        res = await app.context.upstream_session.elicit(
            message=f"Do you want to {input}?",
            requestedSchema=schema,
        )
        direct_text = f"accepted={getattr(res, 'action', '')}"

        app.logger.info(
            "[workflow-mode] Elicitation result",
            data={"res": direct_text},
        )
        return WorkflowResult(value=res)


@app.workflow
class NotificationsWorkflow(Workflow[str]):
    """Temporal workflow that triggers non-logging notifications via proxy."""

    @app.workflow_run
    async def run(self, input: str = "notifications-demo") -> WorkflowResult[str]:
        app.logger.info(
            "[workflow-mode] NotificationsWorkflow starting; sending notifications via SessionProxy",
            data={"path": "mcp_relay_notify activity"},
        )
        # These calls occur inside workflow and will use SessionProxy -> mcp_relay_notify activity
        app.logger.info(
            "[workflow-mode] send_progress_notification",
            data={"token": f"{input}-token", "progress": 0.25},
        )
        await app.context.upstream_session.send_progress_notification(
            progress_token=f"{input}-token", progress=0.25, message="Quarter complete"
        )
        app.logger.info("[workflow-mode] send_resource_list_changed")
        await app.context.upstream_session.send_resource_list_changed()
        return WorkflowResult(value="ok")


async def main():
    async with app.run() as agent_app:
        # Create the MCP server that exposes both workflows and agent configurations
        mcp_server = create_mcp_server_for_app(agent_app)

        # Run the server
        await mcp_server.run_sse_async()


if __name__ == "__main__":
    asyncio.run(main())
