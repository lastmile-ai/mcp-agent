"""Connect two clients concurrently to demonstrate context isolation."""

from __future__ import annotations

import asyncio
from datetime import timedelta
from typing import Any

from anyio.streams.memory import MemoryObjectReceiveStream, MemoryObjectSendStream
from mcp import ClientSession

from mcp_agent.app import MCPApp
from mcp_agent.config import MCPServerSettings, MCPSettings, Settings
from mcp_agent.core.context import Context
from mcp_agent.mcp.gen_client import gen_client
from mcp_agent.mcp.mcp_agent_client_session import MCPAgentClientSession


SERVER_NAME = "context-isolation-server"
SERVER_URL = "http://127.0.0.1:8000/sse"


async def run_client(
    client_name: str,
    log_level: str,
    payloads: list[str],
    *,
    delay_between_calls: float = 0.5,
) -> None:
    """Connect to the server, set logging, and invoke the emit_log tool for each payload."""

    settings = Settings(
        execution_engine="asyncio",
        mcp=MCPSettings(
            servers={
                SERVER_NAME: MCPServerSettings(
                    name=SERVER_NAME,
                    description="Context isolation demo server",
                    transport="sse",
                    url=SERVER_URL,
                )
            }
        ),
    )

    app = MCPApp(name=f"client-{client_name}", settings=settings)

    async with app.run() as running_app:
        context = running_app.context

        async def on_log(params: Any) -> None:
            try:
                message = params.data.get("message") if params.data else None
            except Exception:
                message = None
            print(f"[{client_name}] log {params.level}: {message}")

        class DemoClientSession(MCPAgentClientSession):
            async def _received_notification(self, notification):  # type: ignore[override]
                method = getattr(getattr(notification, "root", None), "method", None)
                if method and method != "notifications/message":
                    print(
                        f"[{client_name}] notify {method}: {notification.model_dump()}"
                    )
                return await super()._received_notification(notification)

        def make_session(
            read_stream: MemoryObjectReceiveStream,
            write_stream: MemoryObjectSendStream,
            read_timeout_seconds: timedelta | None,
            context: Context | None = None,
        ) -> ClientSession:
            return DemoClientSession(
                read_stream=read_stream,
                write_stream=write_stream,
                read_timeout_seconds=read_timeout_seconds,
                logging_callback=on_log,
                context=context,
            )

        async with gen_client(
            SERVER_NAME,
            context.server_registry,
            client_session_factory=make_session,
        ) as server:
            await server.set_logging_level(log_level)
            for idx, payload in enumerate(payloads, start=1):
                result = await server.call_tool(
                    "emit_log",
                    arguments={"level": log_level, "message": payload},
                )
                print(f"[{client_name}] call {idx} result: {result}")
                await asyncio.sleep(delay_between_calls)


async def main() -> None:
    await asyncio.gather(
        run_client("A", "debug", ["hello from A", "A second info"]),
        run_client("B", "error", ["hello from B", "B second info"]),
    )


if __name__ == "__main__":
    asyncio.run(main())
