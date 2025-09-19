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

from mcp.types import ModelHint, ModelPreferences, SamplingMessage, TextContent
from temporalio.exceptions import ApplicationError

from mcp_agent.agents.agent import Agent
from mcp_agent.app import MCPApp
from mcp_agent.config import MCPServerSettings
from mcp_agent.core.context import Context
from mcp_agent.elicitation.handler import console_elicitation_callback
from mcp_agent.executor.workflow import Workflow, WorkflowResult
from mcp_agent.human_input.console_handler import console_input_callback
from mcp_agent.mcp.gen_client import gen_client
from mcp_agent.server.app_server import create_mcp_server_for_app
from mcp_agent.workflows.llm.augmented_llm_openai import OpenAIAugmentedLLM

# Initialize logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# Create a single FastMCPApp instance (which extends MCPApp)
app = MCPApp(
    name="basic_agent_server",
    description="Basic agent server example",
    human_input_callback=console_input_callback,  # for local sampling approval
    elicitation_callback=console_elicitation_callback,  # for local elicitation
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
        app_logger = app.logger

        app_logger.info(
            "[workflow-mode] Starting finder agent in BasicAgentWorkflow.run"
        )
        async with finder_agent:
            finder_llm = await finder_agent.attach_llm(OpenAIAugmentedLLM)

            result = await finder_llm.generate_str(
                message=input,
            )

            # forwards the log to the caller
            app_logger.info(
                f"[workflow-mode] Finder agent completed with result {result}"
            )
            # print to the console (for when running locally)
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
    logger.info("[workflow-mode] Running finder_tool", data={"input": request})

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
        logger.info("[workflow-mode] finder_tool agent result", data={"result": result})

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
        result = f"Workflow successfully resumed! Original message: {message}"
        print(f"Final result: {result}")
        return WorkflowResult(value=result)


@app.workflow_task(name="call_nested_sampling")
async def call_nested_sampling(topic: str) -> str:
    """Activity: call a nested MCP server tool that uses sampling."""
    app_ctx: Context = app.context
    app_ctx.app.logger.info(
        "[activity-mode] call_nested_sampling starting",
        data={"topic": topic},
    )
    nested_name = "nested_sampling"
    nested_path = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "nested_sampling_server.py")
    )
    app_ctx.config.mcp.servers[nested_name] = MCPServerSettings(
        name=nested_name,
        command="uv",
        args=["run", nested_path],
        description="Nested server providing a haiku generator using sampling",
    )

    async with gen_client(
        nested_name, app_ctx.server_registry, context=app_ctx
    ) as client:
        app_ctx.app.logger.info(
            "[activity-mode] call_nested_sampling connected to nested server"
        )
        result = await client.call_tool("get_haiku", {"topic": topic})
        app_ctx.app.logger.info(
            "[activity-mode] call_nested_sampling received result",
            data={"structured": getattr(result, "structuredContent", None)},
        )
    try:
        if result.content and len(result.content) > 0:
            return result.content[0].text or ""
    except Exception:
        pass
    return ""


@app.workflow_task(name="call_nested_elicitation")
async def call_nested_elicitation(action: str) -> str:
    """Activity: call a nested MCP server tool that triggers elicitation."""
    app_ctx: Context = app.context
    app_ctx.app.logger.info(
        "[activity-mode] call_nested_elicitation starting",
        data={"action": action},
    )
    nested_name = "nested_elicitation"
    nested_path = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "nested_elicitation_server.py")
    )
    app_ctx.config.mcp.servers[nested_name] = MCPServerSettings(
        name=nested_name,
        command="uv",
        args=["run", nested_path],
        description="Nested server demonstrating elicitation",
    )

    async with gen_client(
        nested_name, app_ctx.server_registry, context=app_ctx
    ) as client:
        app_ctx.app.logger.info(
            "[activity-mode] call_nested_elicitation connected to nested server"
        )
        result = await client.call_tool("confirm_action", {"action": action})
        app_ctx.app.logger.info(
            "[activity-mode] call_nested_elicitation received result",
            data={"structured": getattr(result, "structuredContent", None)},
        )
    try:
        if result.content and len(result.content) > 0:
            return result.content[0].text or ""
    except Exception:
        pass
    return ""


@app.workflow
class SamplingWorkflow(Workflow[str]):
    """Temporal workflow that triggers an MCP sampling request via a nested server."""

    @app.workflow_run
    async def run(self, input: str = "space exploration") -> WorkflowResult[str]:
        app.logger.info(
            "[workflow-mode] SamplingWorkflow starting",
            data={"note": "direct sampling via SessionProxy, then activity sampling"},
        )
        # 1) Direct workflow sampling via SessionProxy (will schedule mcp_relay_request activity)
        app.logger.info(
            "[workflow-mode] SessionProxy.create_message (direct)",
            data={"path": "mcp_relay_request activity"},
        )
        direct_text = ""
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
                direct_text = (
                    direct.content.text
                    if isinstance(direct.content, TextContent)
                    else ""
                )
            except Exception:
                direct_text = ""
        except Exception as e:
            app.logger.warning(
                "[workflow-mode] Direct sampling failed; continuing with nested",
                data={"error": str(e)},
            )
        app.logger.info(
            "[workflow-mode] Direct sampling result",
            data={"text": direct_text},
        )

        # 2) Nested server sampling executed as an activity
        app.logger.info(
            "[activity-mode] Invoking call_nested_sampling via executor.execute",
            data={"topic": input},
        )
        result = await app.context.executor.execute(call_nested_sampling, input)
        # Log and return
        app.logger.info(
            "[activity-mode] Nested sampling result",
            data={"text": result},
        )
        return WorkflowResult(value=f"direct={direct_text}\nnested={result}")


@app.workflow
class ElicitationWorkflow(Workflow[str]):
    """Temporal workflow that triggers elicitation via direct session and nested server."""

    @app.workflow_run
    async def run(self, input: str = "proceed") -> WorkflowResult[str]:
        app.logger.info(
            "[workflow-mode] ElicitationWorkflow starting",
            data={"note": "direct elicit via SessionProxy, then activity elicitation"},
        )

        # 1) Direct elicitation via SessionProxy (schedules mcp_relay_request)
        schema = {
            "type": "object",
            "properties": {"confirm": {"type": "boolean"}},
            "required": ["confirm"],
        }
        app.logger.info(
            "[workflow-mode] SessionProxy.elicit (direct)",
            data={"path": "mcp_relay_request activity"},
        )
        direct = await app.context.upstream_session.elicit(
            message=f"Do you want to {input}?",
            requestedSchema=schema,
        )
        direct_text = f"accepted={getattr(direct, 'action', '')}"

        # 2) Nested elicitation via activity
        app.logger.info(
            "[activity-mode] Invoking call_nested_elicitation via executor.execute",
            data={"action": input},
        )
        nested = await app.context.executor.execute(call_nested_elicitation, input)

        app.logger.info(
            "[workflow-mode] Elicitation results",
            data={"direct": direct_text, "nested": nested},
        )
        return WorkflowResult(value=f"direct={direct_text}\nnested={nested}")


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
