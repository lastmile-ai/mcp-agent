"""
Elicitation Server (asyncio)

Demonstrates user confirmation via elicitation.

Run:
  uv run server.py
"""

from __future__ import annotations

import asyncio
from typing import Optional

from mcp_agent.app import MCPApp
from mcp_agent.core.context import Context as AppContext
from mcp_agent.server.app_server import create_mcp_server_for_app
from mcp_agent.human_input.handler import console_input_callback
from mcp_agent.elicitation.handler import console_elicitation_callback
from mcp.types import ElicitRequestedSchema
from pydantic import BaseModel, Field


app = MCPApp(
    name="elicitation_server",
    description="Minimal server showing elicitation (user confirmation)",
    human_input_callback=console_input_callback,
    elicitation_callback=console_elicitation_callback,
)


@app.tool(name="confirm_action")
async def confirm_action(action: str, app_ctx: Optional[AppContext] = None) -> str:
    """Ask the user to confirm an action."""
    _app = app_ctx.app if app_ctx else app
    upstream = getattr(_app.context, "upstream_session", None)

    class ConfirmBooking(BaseModel):
        confirm: bool = Field(description="Confirm action?")
        notes: str = Field(default="", description="Optional notes")

    schema: ElicitRequestedSchema = ConfirmBooking.model_json_schema()
    if upstream is not None:
        result = await upstream.elicit(
            message=f"Do you want to {action}?", requestedSchema=schema
        )
        if getattr(result, "action", "") in ("accept", "accepted"):
            data = ConfirmBooking.model_validate(getattr(result, "content", {}))
            return (
                f"Action '{action}' confirmed. Notes: {data.notes or 'None'}"
                if data.confirm
                else f"Action '{action}' cancelled"
            )
        if getattr(result, "action", "") == "decline":
            return "Action declined"
        return "Action cancelled"
    # Fallback to console handler
    if _app.context.elicitation_handler:
        resp = await _app.context.elicitation_handler(
            {"message": f"Do you want to {action}?", "requestedSchema": schema}
        )
        if getattr(resp, "action", "") in ("accept", "accepted"):
            data = ConfirmBooking.model_validate(getattr(resp, "content", {}))
            return (
                f"Action '{action}' confirmed. Notes: {data.notes or 'None'}"
                if data.confirm
                else f"Action '{action}' cancelled"
            )
        if getattr(resp, "action", "") == "decline":
            return "Action declined"
        return "Action cancelled"
    return f"Action '{action}' confirmed by default"


async def main() -> None:
    async with app.run() as agent_app:
        mcp_server = create_mcp_server_for_app(agent_app)
        await mcp_server.run_sse_async()


if __name__ == "__main__":
    asyncio.run(main())
