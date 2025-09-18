"""
Minimal client for the Elicitation Server.

Run:
  uv run client.py
"""

from __future__ import annotations

import asyncio
from datetime import timedelta
from typing import Optional

from mcp_agent.app import MCPApp
from mcp_agent.core.context import Context
from mcp_agent.config import Settings
from mcp_agent.mcp.mcp_agent_client_session import MCPAgentClientSession
from mcp_agent.mcp.gen_client import gen_client
from mcp_agent.human_input.handler import console_input_callback
from mcp_agent.elicitation.handler import console_elicitation_callback
from anyio.streams.memory import MemoryObjectReceiveStream, MemoryObjectSendStream
from mcp import ClientSession
from mcp.types import LoggingMessageNotificationParams


def _make_session(
    read_stream: MemoryObjectReceiveStream,
    write_stream: MemoryObjectSendStream,
    read_timeout_seconds: timedelta | None,
    context: Optional[Context] = None,
) -> ClientSession:
    async def on_server_log(params: LoggingMessageNotificationParams) -> None:
        level = params.level.upper()
        name = params.logger or "server"
        print(f"[SERVER LOG] [{level}] [{name}] {params.data}")

    return MCPAgentClientSession(
        read_stream=read_stream,
        write_stream=write_stream,
        read_timeout_seconds=read_timeout_seconds,
        logging_callback=on_server_log,
        context=context,
    )


async def main() -> None:
    settings = Settings(execution_engine="asyncio")
    app = MCPApp(
        name="elicitation_client",
        human_input_callback=console_input_callback,
        elicitation_callback=console_elicitation_callback,
        settings=settings,
    )

    async with app.run() as client_app:
        # Configure server entry
        cfg = type("Cfg", (), {})()
        cfg.name = "elicitation_server"
        cfg.transport = "sse"
        cfg.url = "http://127.0.0.1:8000/sse"
        client_app.context.server_registry.registry["elicitation_server"] = cfg

        async with gen_client(
            "elicitation_server",
            client_app.context.server_registry,
            client_session_factory=_make_session,
            context=client_app.context,
        ) as server:
            await server.set_logging_level("info")
            res = await server.call_tool("confirm_action", {"action": "proceed"})
            print("confirm_action:", res.content[0].text if res.content else None)


if __name__ == "__main__":
    asyncio.run(main())
