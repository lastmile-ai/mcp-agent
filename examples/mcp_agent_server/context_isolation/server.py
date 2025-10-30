"""Simple SSE server demonstrating per-client context isolation."""

import asyncio

from mcp_agent.app import MCPApp
from mcp_agent.core.context import Context
from mcp_agent.server.app_server import create_mcp_server_for_app


app = MCPApp(name="context-isolation-server")


@app.tool("emit_log")
async def emit_log(context: Context, level: str = "info", message: str = "hi") -> dict:
    """Log a message at the requested level and emit a notification."""

    session = context.request_session_id or "unknown"
    await context.log(level, f"[{session}] {message}")
    try:
        await context.send_notification(
            "demo/echo",
            {
                "session": session,
                "level": level,
                "message": message,
            },
        )
    except Exception:
        pass
    return {"logged": message, "level": level, "session": session}


async def main() -> None:
    async with app.run() as running_app:
        server = create_mcp_server_for_app(running_app)
        await server.run_sse_async()


if __name__ == "__main__":
    asyncio.run(main())
