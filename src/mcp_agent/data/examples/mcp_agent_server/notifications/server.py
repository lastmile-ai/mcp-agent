"""
Notifications Server (asyncio)

Demonstrates logging and non-logging notifications.

Run:
  uv run server.py
"""

from __future__ import annotations

import asyncio
from typing import Optional, Literal

from mcp_agent.app import MCPApp
from mcp_agent.core.context import Context as AppContext
from mcp_agent.server.app_server import create_mcp_server_for_app


app = MCPApp(
    name="notifications_server",
    description="Minimal server showing notifications and logging",
)


@app.tool(name="notify")
def notify(
    message: str,
    level: Literal["debug", "info", "warning", "error"] = "info",
    app_ctx: Optional[AppContext] = None,
) -> str:
    """Send an upstream log/notification at the requested level."""
    _app = app_ctx.app if app_ctx else app
    logger = _app.logger
    if level == "debug":
        logger.debug(message)
    elif level == "warning":
        logger.warning(message)
    elif level == "error":
        logger.error(message)
    else:
        logger.info(message)
    return "ok"


@app.tool(name="notify_progress")
async def notify_progress(
    progress: float = 0.5,
    message: str | None = "Demo progress",
    app_ctx: Optional[AppContext] = None,
) -> str:
    """Send a progress notification via upstream session (best-effort)."""
    _app = app_ctx.app if app_ctx else app
    upstream = getattr(_app.context, "upstream_session", None)
    if upstream is None:
        _app.logger.warning("No upstream session to notify")
        return "no-upstream"
    await upstream.send_progress_notification(
        progress_token="notifications-demo", progress=progress, message=message
    )
    _app.logger.info("Sent notifications/progress")
    return "ok"


async def main() -> None:
    async with app.run() as agent_app:
        mcp_server = create_mcp_server_for_app(agent_app)
        await mcp_server.run_sse_async()


if __name__ == "__main__":
    asyncio.run(main())
