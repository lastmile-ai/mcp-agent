"""
Minimal client for the OAuth interactive demo. It connects to the MCP server,
invokes the GitHub organization search tool, and responds to auth/request
messages by opening the browser and completing the OAuth flow.
"""

from __future__ import annotations

import asyncio
from datetime import timedelta

from anyio.streams.memory import MemoryObjectReceiveStream, MemoryObjectSendStream
from rich import print

from mcp import ClientSession
from mcp.types import LoggingMessageNotificationParams

from mcp_agent.app import MCPApp
from mcp_agent.config import MCPServerSettings
from mcp_agent.core.context import Context
from mcp_agent.elicitation.handler import console_elicitation_callback
from mcp_agent.human_input.console_handler import console_input_callback
from mcp_agent.mcp.gen_client import gen_client
from mcp_agent.mcp.mcp_agent_client_session import MCPAgentClientSession


class LoggingClientSession(MCPAgentClientSession):
    async def _received_notification(self, notification):  # type: ignore[override]
        method = getattr(notification.root, "method", None)
        if method and method != "notifications/message":
            try:
                payload = notification.model_dump()
            except Exception:
                payload = str(notification)
            print(f"[SERVER NOTIFY] {method}: {payload}")
        return await super()._received_notification(notification)


def make_session(
    read_stream: MemoryObjectReceiveStream,
    write_stream: MemoryObjectSendStream,
    read_timeout_seconds: timedelta | None,
    context: Context | None = None,
) -> ClientSession:
    async def on_server_log(params: LoggingMessageNotificationParams) -> None:
        level = params.level.upper()
        logger_name = params.logger or "server"
        print(f"[SERVER LOG] [{level}] [{logger_name}] {params.data}")

    return LoggingClientSession(
        read_stream=read_stream,
        write_stream=write_stream,
        read_timeout_seconds=read_timeout_seconds,
        logging_callback=on_server_log,
        context=context,
    )


async def main() -> None:
    app = MCPApp(
        name="github_oauth_client",
        human_input_callback=console_input_callback,
        elicitation_callback=console_elicitation_callback,
    )

    async with app.run() as client_app:
        registry = client_app.context.server_registry
        registry.registry["github_demo"] = MCPServerSettings(
            name="github_demo",
            description="Local GitHub OAuth demo server",
            transport="sse",
            url="http://127.0.0.1:8000/sse",
        )

        async with gen_client(
            "github_demo",
            registry,
            client_session_factory=make_session,
            context=client_app.context,
        ) as connection:
            try:
                await connection.set_logging_level("info")
            except Exception:
                print("[client] Server does not support logging/setLevel")

            print("[client] Invoking github_org_search...")
            result = await connection.call_tool(
                "github_org_search",
                {"query": "lastmile-ai"},
            )
            print("[client] Result:")
            for item in result.content or []:
                print(item)


if __name__ == "__main__":
    asyncio.run(main())
