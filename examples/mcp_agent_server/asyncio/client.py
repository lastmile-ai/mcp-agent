import argparse
import asyncio
import json
import time
from datetime import timedelta
from anyio.streams.memory import MemoryObjectReceiveStream, MemoryObjectSendStream
from mcp import ClientSession
from mcp.types import CallToolResult, LoggingMessageNotificationParams
from mcp_agent.app import MCPApp
from mcp_agent.config import MCPServerSettings
from mcp_agent.core.context import Context
from mcp_agent.executor.workflow import WorkflowExecution
from mcp_agent.mcp.gen_client import gen_client
from mcp_agent.mcp.mcp_agent_client_session import MCPAgentClientSession
from mcp_agent.human_input.console_handler import console_input_callback
from mcp_agent.elicitation.handler import console_elicitation_callback

from rich import print

try:
    from exceptiongroup import ExceptionGroup as _ExceptionGroup  # Python 3.10 backport
except Exception:  # pragma: no cover
    _ExceptionGroup = None  # type: ignore
try:
    from anyio import BrokenResourceError as _BrokenResourceError
except Exception:  # pragma: no cover
    _BrokenResourceError = None  # type: ignore


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--custom-fastmcp-settings",
        action="store_true",
        help="Enable custom FastMCP settings for the server",
    )
    parser.add_argument(
        "--server-log-level",
        type=str,
        default=None,
        help="Set initial server logging level (debug, info, notice, warning, error, critical, alert, emergency)",
    )
    parser.add_argument(
        "--features",
        nargs="+",
        choices=[
            "workflows",
            "tools",
            "sampling",
            "elicitation",
            "notifications",
            "all",
        ],
        default=["all"],
        help="Select which features to test",
    )
    args = parser.parse_args()
    use_custom_fastmcp_settings = args.custom_fastmcp_settings
    selected = set(args.features)
    if "all" in selected:
        selected = {"workflows", "tools", "sampling", "elicitation", "notifications"}

    # Create MCPApp to get the server registry
    app = MCPApp(
        name="workflow_mcp_client",
        human_input_callback=console_input_callback,
        elicitation_callback=console_elicitation_callback,
    )
    async with app.run() as client_app:
        logger = client_app.logger
        context = client_app.context

        # Connect to the workflow server
        logger.info("Connecting to workflow server...")

        # Override the server configuration to point to our local script
        run_server_args = ["run", "main.py"]
        if use_custom_fastmcp_settings:
            logger.info("Using custom FastMCP settings for the server.")
            run_server_args += ["--custom-fastmcp-settings"]
        else:
            logger.info("Using default FastMCP settings for the server.")
        context.server_registry.registry["basic_agent_server"] = MCPServerSettings(
            name="basic_agent_server",
            description="Local workflow server running the basic agent example",
            command="uv",
            args=run_server_args,
        )

        # Define a logging callback to receive server-side log notifications
        async def on_server_log(params: LoggingMessageNotificationParams) -> None:
            level = params.level.upper()
            name = params.logger or "server"
            print(f"[SERVER LOG] [{level}] [{name}] {params.data}")

        # Provide a client session factory that installs our logging callback
        # and prints non-logging notifications to the console
        class ConsolePrintingClientSession(MCPAgentClientSession):
            async def _received_notification(self, notification):  # type: ignore[override]
                try:
                    method = getattr(notification.root, "method", None)
                except Exception:
                    method = None

                # Avoid duplicating server log prints (handled by logging_callback)
                if method and method != "notifications/message":
                    try:
                        data = notification.model_dump()
                    except Exception:
                        data = str(notification)
                    print(f"[SERVER NOTIFY] {method}: {data}")

                return await super()._received_notification(notification)

        def make_session(
            read_stream: MemoryObjectReceiveStream,
            write_stream: MemoryObjectSendStream,
            read_timeout_seconds: timedelta | None,
            context: Context | None = None,
        ) -> ClientSession:
            return ConsolePrintingClientSession(
                read_stream=read_stream,
                write_stream=write_stream,
                read_timeout_seconds=read_timeout_seconds,
                logging_callback=on_server_log,
                context=context,
            )

        try:
            async with gen_client(
                "basic_agent_server",
                context.server_registry,
                client_session_factory=make_session,
            ) as server:
                # Ask server to send logs at the requested level (default info)
                level = (args.server_log_level or "info").lower()
                print(f"[client] Setting server logging level to: {level}")
                try:
                    await server.set_logging_level(level)
                except Exception:
                    # Older servers may not support logging capability
                    print("[client] Server does not support logging/setLevel")

                # List available tools
                tools_result = await server.list_tools()
                logger.info(
                    "Available tools:",
                    data={"tools": [tool.name for tool in tools_result.tools]},
                )

                # List available workflows
                if "workflows" in selected:
                    logger.info("Fetching available workflows...")
                    workflows_response = await server.call_tool("workflows-list", {})
                    logger.info(
                        "Available workflows:",
                        data=_tool_result_to_json(workflows_response)
                        or workflows_response,
                    )

                # Call the BasicAgentWorkflow (run + status)
                if "workflows" in selected:
                    run_result = await server.call_tool(
                        "workflows-BasicAgentWorkflow-run",
                        arguments={
                            "run_parameters": {
                                "input": "Print the first two paragraphs of https://modelcontextprotocol.io/introduction."
                            }
                        },
                    )

                    # Tolerant parsing of run IDs from tool result
                    run_payload = _tool_result_to_json(run_result)
                    if not run_payload:
                        sc = getattr(run_result, "structuredContent", None)
                        if isinstance(sc, dict):
                            run_payload = sc.get("result") or sc
                    if not run_payload:
                        # Last resort: parse unstructured content if present and non-empty
                        if (
                            getattr(run_result, "content", None)
                            and run_result.content[0].text
                        ):
                            run_payload = json.loads(run_result.content[0].text)
                        else:
                            raise RuntimeError(
                                "Unable to extract workflow run IDs from tool result"
                            )

                    execution = WorkflowExecution(**run_payload)
                    run_id = execution.run_id
                    logger.info(
                        f"Started BasicAgentWorkflow-run. workflow ID={execution.workflow_id}, run ID={run_id}"
                    )

                    # Wait for the workflow to complete
                    while True:
                        get_status_result = await server.call_tool(
                            "workflows-BasicAgentWorkflow-get_status",
                            arguments={"run_id": run_id},
                        )

                        # Tolerant parsing of get_status result
                        workflow_status = _tool_result_to_json(get_status_result)
                        if workflow_status is None:
                            sc = getattr(get_status_result, "structuredContent", None)
                            if isinstance(sc, dict):
                                workflow_status = sc.get("result") or sc
                        if workflow_status is None:
                            logger.error(
                                f"Failed to parse workflow status response: {get_status_result}"
                            )
                            break

                        logger.info(
                            f"Workflow run {run_id} status:",
                            data=workflow_status,
                        )

                        if not workflow_status.get("status"):
                            logger.error(
                                f"Workflow run {run_id} status is empty. get_status_result:",
                                data=get_status_result,
                            )
                            break

                        if workflow_status.get("status") == "completed":
                            logger.info(
                                f"Workflow run {run_id} completed successfully! Result:",
                                data=workflow_status.get("result"),
                            )
                            break
                        elif workflow_status.get("status") == "error":
                            logger.error(
                                f"Workflow run {run_id} failed with error:",
                                data=workflow_status,
                            )
                            break
                        elif workflow_status.get("status") == "running":
                            logger.info(
                                f"Workflow run {run_id} is still running...",
                            )
                        elif workflow_status.get("status") == "cancelled":
                            logger.error(
                                f"Workflow run {run_id} was cancelled.",
                                data=workflow_status,
                            )
                            break
                        else:
                            logger.error(
                                f"Unknown workflow status: {workflow_status.get('status')}",
                                data=workflow_status,
                            )
                            break

                        await asyncio.sleep(5)

                    # Get the token usage summary
                    logger.info("Fetching token usage summary...")
                    token_usage_result = await server.call_tool(
                        "get_token_usage",
                        arguments={
                            "run_id": run_id,
                            "workflow_id": execution.workflow_id,
                        },
                    )

                    logger.info(
                        "Token usage summary:",
                        data=_tool_result_to_json(token_usage_result)
                        or token_usage_result,
                    )

                    # Display the token usage summary
                    print(token_usage_result.structuredContent)

                    await asyncio.sleep(1)

                # Call the sync tool 'grade_story' separately (no run/status loop)
                if "tools" in selected:
                    try:
                        grade_result = await server.call_tool(
                            "grade_story",
                            arguments={"story": "This is a test story."},
                        )
                        grade_payload = _tool_result_to_json(grade_result) or (
                            (
                                grade_result.structuredContent.get("result")
                                if getattr(grade_result, "structuredContent", None)
                                else None
                            )
                            or (
                                grade_result.content[0].text
                                if grade_result.content
                                else None
                            )
                        )
                        logger.info("grade_story result:", data=grade_payload)
                    except Exception as e:
                        logger.error("grade_story call failed", data=str(e))

                # Call the async tool 'grade_story_async': start then poll status
                if "tools" in selected:
                    try:
                        async_run_result = await server.call_tool(
                            "grade_story_async",
                            arguments={"story": "This is a test story."},
                        )
                        async_ids = (
                            (
                                getattr(async_run_result, "structuredContent", {}) or {}
                            ).get("result")
                            or _tool_result_to_json(async_run_result)
                            or json.loads(async_run_result.content[0].text)
                        )
                        async_run_id = async_ids["run_id"]
                        logger.info(
                            f"Started grade_story_async. run ID={async_run_id}",
                        )

                        # Poll status until completion
                        while True:
                            async_status = await server.call_tool(
                                "workflows-get_status",
                                arguments={"run_id": async_run_id},
                            )
                            async_status_json = (
                                getattr(async_status, "structuredContent", {}) or {}
                            ).get("result") or _tool_result_to_json(async_status)
                            if async_status_json is None:
                                logger.error(
                                    "grade_story_async: failed to parse status",
                                    data=async_status,
                                )
                                break
                            logger.info(
                                "grade_story_async status:", data=async_status_json
                            )
                            if async_status_json.get("status") in (
                                "completed",
                                "error",
                                "cancelled",
                            ):
                                break
                            await asyncio.sleep(2)
                    except Exception as e:
                        logger.error("grade_story_async call failed", data=str(e))

                # Sampling demo via app.tool
                if "sampling" in selected:
                    try:
                        demo = await server.call_tool(
                            "sampling_demo", arguments={"topic": "flowers"}
                        )
                        logger.info(
                            "sampling_demo result:",
                            data=_tool_result_to_json(demo) or demo,
                        )
                    except Exception as e:
                        logger.error("sampling_demo failed", data=str(e))

                # Elicitation demo via app.tool
                if "elicitation" in selected:
                    try:
                        el = await server.call_tool(
                            "elicitation_demo", arguments={"action": "proceed"}
                        )
                        logger.info(
                            "elicitation_demo result:",
                            data=_tool_result_to_json(el) or el,
                        )
                    except Exception as e:
                        logger.error("elicitation_demo failed", data=str(e))

                # Notifications demo via app.tool
                if "notifications" in selected:
                    try:
                        n1 = await server.call_tool("notify_resources", arguments={})
                        logger.info(
                            "notify_resources result:",
                            data=_tool_result_to_json(n1) or n1,
                        )
                        n2 = await server.call_tool(
                            "notify_progress",
                            arguments={"progress": 0.5, "message": "Halfway there"},
                        )
                        logger.info(
                            "notify_progress result:",
                            data=_tool_result_to_json(n2) or n2,
                        )
                    except Exception as e:
                        logger.error("notifications demo failed", data=str(e))
        except Exception as e:
            # Tolerate benign shutdown races from stdio client (BrokenResourceError within ExceptionGroup)
            if _ExceptionGroup is not None and isinstance(e, _ExceptionGroup):
                subs = getattr(e, "exceptions", []) or []
                if (
                    _BrokenResourceError is not None
                    and subs
                    and all(isinstance(se, _BrokenResourceError) for se in subs)
                ):
                    logger.debug("Ignored BrokenResourceError from stdio shutdown")
                else:
                    raise
            elif _BrokenResourceError is not None and isinstance(
                e, _BrokenResourceError
            ):
                logger.debug("Ignored BrokenResourceError from stdio shutdown")
            elif "BrokenResourceError" in str(e):
                logger.debug(
                    "Ignored BrokenResourceError from stdio shutdown (string match)"
                )
            else:
                raise
        # Nudge cleanup of subprocess transports before the loop closes to avoid
        # 'Event loop is closed' from BaseSubprocessTransport.__del__ on GC.
        try:
            await asyncio.sleep(0)
        except Exception:
            pass
        try:
            import gc

            gc.collect()
        except Exception:
            pass


def _tool_result_to_json(tool_result: CallToolResult):
    if tool_result.content and len(tool_result.content) > 0:
        text = tool_result.content[0].text
        try:
            # Try to parse the response as JSON if it's a string
            import json

            return json.loads(text)
        except (json.JSONDecodeError, TypeError):
            # If it's not valid JSON, just use the text
            return None


if __name__ == "__main__":
    start = time.time()
    asyncio.run(main())
    end = time.time()
    t = end - start

    print(f"Total run time: {t:.2f}s")
