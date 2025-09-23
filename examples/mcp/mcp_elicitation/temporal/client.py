import asyncio
import json
import time
from mcp_agent.app import MCPApp
from mcp_agent.config import Settings, LoggerSettings, MCPSettings
import yaml
from mcp_agent.elicitation.handler import console_elicitation_callback
from mcp_agent.config import MCPServerSettings
from mcp_agent.core.context import Context
from mcp_agent.executor.workflow import WorkflowExecution
from mcp_agent.mcp.gen_client import gen_client
from datetime import timedelta
from anyio.streams.memory import MemoryObjectReceiveStream, MemoryObjectSendStream
from mcp import ClientSession
from mcp_agent.mcp.mcp_agent_client_session import MCPAgentClientSession
from mcp.types import CallToolResult, LoggingMessageNotificationParams
from mcp_agent.human_input.console_handler import console_input_callback

try:
    from exceptiongroup import ExceptionGroup as _ExceptionGroup  # Python 3.10 backport
except Exception:  # pragma: no cover
    _ExceptionGroup = None  # type: ignore
try:
    from anyio import BrokenResourceError as _BrokenResourceError
except Exception:  # pragma: no cover
    _BrokenResourceError = None  # type: ignore


async def main():
    # Create MCPApp to get the server registry, with console handlers
    # IMPORTANT: This client acts as the “upstream MCP client” for the server.
    # When the server requests sampling (sampling/createMessage), the client-side
    # MCPApp must be able to service that request locally (approval prompts + LLM call).
    # Those client-local flows are not running inside a Temporal workflow, so they
    # must use the asyncio executor. If this were set to "temporal", local sampling
    # would crash with: "TemporalExecutor.execute must be called from within a workflow".
    #
    # We programmatically construct Settings here (mirroring examples/basic/mcp_basic_agent/main.py)
    # so everything is self-contained in this client:
    settings = Settings(
        execution_engine="asyncio",
        logger=LoggerSettings(level="info"),
        mcp=MCPSettings(
            servers={
                "basic_agent_server": MCPServerSettings(
                    name="basic_agent_server",
                    description="Local workflow server running the basic agent example",
                    transport="sse",
                    # Use a routable loopback host; 0.0.0.0 is a bind address, not a client URL
                    url="http://127.0.0.1:8000/sse",
                )
            }
        ),
    )
    # Load secrets (API keys, etc.) if a secrets file is available and merge into settings.
    # We intentionally deep-merge the secrets on top of our base settings so
    # credentials are applied without overriding our executor or server endpoint.
    try:
        secrets_path = Settings.find_secrets()
        if secrets_path and secrets_path.exists():
            with open(secrets_path, "r", encoding="utf-8") as f:
                secrets_dict = yaml.safe_load(f) or {}

            def _deep_merge(base: dict, overlay: dict) -> dict:
                out = dict(base)
                for k, v in (overlay or {}).items():
                    if k in out and isinstance(out[k], dict) and isinstance(v, dict):
                        out[k] = _deep_merge(out[k], v)
                    else:
                        out[k] = v
                return out

            base_dict = settings.model_dump(mode="json")
            merged = _deep_merge(base_dict, secrets_dict)
            settings = Settings(**merged)
    except Exception:
        # Best-effort: continue without secrets if parsing fails
        pass
    app = MCPApp(
        name="workflow_mcp_client",
        # Disable sampling approval prompts entirely to keep flows non-interactive.
        # Elicitation remains interactive via console_elicitation_callback.
        human_input_callback=console_input_callback,
        elicitation_callback=console_elicitation_callback,
        settings=settings,
    )
    async with app.run() as client_app:
        logger = client_app.logger
        context = client_app.context

        # Connect to the workflow server
        try:
            logger.info("Connecting to workflow server...")

            # Server connection is configured via Settings above (no runtime mutation needed)

            # Connect to the workflow server
            # Define a logging callback to receive server-side log notifications
            async def on_server_log(params: LoggingMessageNotificationParams) -> None:
                # Pretty-print server logs locally for demonstration
                level = params.level.upper()
                name = params.logger or "server"
                # params.data can be any JSON-serializable data
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

            # Connect to the workflow server
            async with gen_client(
                "basic_agent_server",
                context.server_registry,
                client_session_factory=make_session,
            ) as server:
                # Ask server to send logs at the requested level (default info)
                level = "info"
                print(f"[client] Setting server logging level to: {level}")
                try:
                    await server.set_logging_level(level)
                except Exception:
                    # Older servers may not support logging capability
                    print("[client] Server does not support logging/setLevel")

                # Call the `book_table` tool defined via `@app.tool`
                run_result = await server.call_tool(
                    "book_table",
                    arguments={"date": "today", "party_size": 2, "topic": "autumn"},
                )
                print(f"[client] Workflow run result: {run_result}")

                # Run the `TestWorkflow` workflow...
                run_result = await server.call_tool(
                    "workflows-TestWorkflow-run",
                    arguments={
                        "run_parameters": {
                            "args": {
                                "date": "today",
                                "party_size": 2,
                                "topic": "autumn",
                            }
                        }
                    },
                )

                execution = WorkflowExecution(**json.loads(run_result.content[0].text))
                run_id = execution.run_id
                workflow_id = execution.workflow_id

                # and wait for execution to complete
                while True:
                    get_status_result = await server.call_tool(
                        "workflows-get_status",
                        arguments={"run_id": run_id, "workflow_id": workflow_id},
                    )

                    workflow_status = _tool_result_to_json(get_status_result)
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

        except Exception as e:
            # Tolerate benign shutdown races from SSE client (BrokenResourceError within ExceptionGroup)
            if _ExceptionGroup is not None and isinstance(e, _ExceptionGroup):
                subs = getattr(e, "exceptions", []) or []
                if (
                    _BrokenResourceError is not None
                    and subs
                    and all(isinstance(se, _BrokenResourceError) for se in subs)
                ):
                    logger.debug("Ignored BrokenResourceError from SSE shutdown")
                else:
                    raise
            elif _BrokenResourceError is not None and isinstance(
                e, _BrokenResourceError
            ):
                logger.debug("Ignored BrokenResourceError from SSE shutdown")
            elif "BrokenResourceError" in str(e):
                logger.debug(
                    "Ignored BrokenResourceError from SSE shutdown (string match)"
                )
            else:
                raise


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
