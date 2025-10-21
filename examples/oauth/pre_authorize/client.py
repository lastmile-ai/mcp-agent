import asyncio
import json
import os
import sys
import time

from datetime import timedelta
from anyio.streams.memory import MemoryObjectReceiveStream, MemoryObjectSendStream
from mcp import ClientSession
from mcp.types import CallToolResult, LoggingMessageNotificationParams
from mcp_agent.app import MCPApp
from mcp_agent.config import MCPServerSettings
from mcp_agent.core.context import Context
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

# Get GitHub access token from environment or ask user
access_token = os.getenv("GITHUB_ACCESS_TOKEN")

if not access_token:
    print("\nGitHub access token not found in environment variable GITHUB_ACCESS_TOKEN")
    print("\nTo get a GitHub access token:")
    print("1. Run the oauth_demo.py script from examples/oauth/ to get a fresh token")
    print("2. Or go to GitHub Settings > Developer settings > Personal access tokens")
    print("3. Create a token with 'read:org' and 'public_repo' scopes")
    print("\nThen set the token:")
    print("export GITHUB_ACCESS_TOKEN='your_token_here'")

# Verify token format
if not access_token.startswith(("gho_", "ghp_", "github_pat_")):
    print(
        f"Warning: Token doesn't look like a GitHub token (got: {access_token[:10]}...)"
    )
    print("GitHub tokens usually start with 'gho_', 'ghp_', or 'github_pat_'")


async def main():
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
        context.server_registry.registry["pre_authorize_server"] = MCPServerSettings(
            name="pre_authorize_server",
            description="Local workflow server running the pre-authorize example",
            transport="sse",
            url="http://127.0.0.1:8000/sse",
            # command="uv",
            # args=["run", "main.py"],
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
                "pre_authorize_server",
                context.server_registry,
                client_session_factory=make_session,
            ) as server:
                try:
                    await server.set_logging_level("info")
                except Exception:
                    # Older servers may not support logging capability
                    print("[client] Server does not support logging/setLevel")

                # List available tools
                tools_result = await server.list_tools()
                logger.info(
                    "Available tools:",
                    data={"tools": [tool.name for tool in tools_result.tools]},
                )

                if len(sys.argv) < 2 or sys.argv[1] != "--skip-store-credentials":
                    print("Storing workflow credentials")
                    await server.call_tool(
                        "workflows-store-credentials",
                        arguments={
                            "workflow_name": "github_org_search",
                            "tokens": [
                                {
                                    "access_token": access_token,
                                    "server_name": "github",
                                }
                            ],
                        },
                    )

                tool_result = await server.call_tool(
                    "github_org_search", {"query": "lastmile-ai"}
                )
                parsed = _tool_result_to_json(tool_result)
                if parsed is not None:
                    print(json.dumps(parsed, indent=2))
                else:
                    print(tool_result)
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
