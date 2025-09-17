"""
Reference Agent Server (asyncio)

Demonstrates:
  - Agent behavior with MCP servers (fetch + filesystem) and an LLM
  - Tools using @app.tool and @app.async_tool
  - Notifications and logging via app.logger
  - Elicitation (user confirmation) proxied to upstream client
  - Sampling (LLM request) with simple RequestParams
  - Prompts and Resources registered on the FastMCP server

Run:
  uv run server.py

Test client:
  uv run client.py
"""

from __future__ import annotations

import asyncio
import os
from typing import Optional, Literal

from mcp_agent.app import MCPApp
from mcp_agent.core.context import Context as AppContext
from mcp_agent.server.app_server import create_mcp_server_for_app
from mcp_agent.human_input.handler import console_input_callback
from mcp_agent.elicitation.handler import console_elicitation_callback

from mcp_agent.agents.agent import Agent
from mcp_agent.workflows.factory import create_llm
from mcp_agent.workflows.llm.augmented_llm_openai import OpenAIAugmentedLLM
from mcp_agent.workflows.llm.augmented_llm import RequestParams as LLMRequestParams
from mcp_agent.workflows.llm.llm_selector import ModelPreferences
from mcp.types import ElicitRequestedSchema
from pydantic import BaseModel, Field


app = MCPApp(
    name="reference_agent_server",
    description="Reference server demonstrating agent + tools + prompts + resources",
    human_input_callback=console_input_callback,
    elicitation_callback=console_elicitation_callback,
)


@app.tool(name="finder_tool")
async def finder_tool(request: str, app_ctx: Optional[AppContext] = None) -> str:
    """Agent that can use filesystem+fetch and an LLM to answer the request."""
    _app = app_ctx.app if app_ctx else app
    ctx = _app.context
    try:
        if "filesystem" in ctx.config.mcp.servers:
            ctx.config.mcp.servers["filesystem"].args.extend([os.getcwd()])
    except Exception:
        pass

    agent = Agent(
        name="finder",
        instruction=(
            "Use MCP servers to fetch and read files, then answer the user's query concisely."
        ),
        server_names=["fetch", "filesystem"],
        context=ctx,
    )
    async with agent:
        llm = await agent.attach_llm(OpenAIAugmentedLLM)
        return await llm.generate_str(message=request)


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


@app.tool(name="confirm_action")
async def confirm_action(
    action: str,
    app_ctx: Optional[AppContext] = None,
) -> str:
    """Ask the user to confirm the action via elicitation."""
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

    # Fallback to handler if present
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


@app.tool(name="sample_haiku")
async def sample_haiku(topic: str, app_ctx: Optional[AppContext] = None) -> str:
    """Generate a short poem using configured LLM settings."""
    _app = app_ctx.app if app_ctx else app
    llm = create_llm(
        agent_name="sampling_demo",
        server_names=[],
        instruction="You are a concise poet.",
        context=_app.context,
    )
    req = LLMRequestParams(
        maxTokens=80,
        modelPreferences=ModelPreferences(hints=[]),
        systemPrompt="Write a 3-line haiku.",
        temperature=0.7,
        use_history=False,
        max_iterations=1,
    )
    return await llm.generate_str(message=f"Haiku about {topic}", request_params=req)


async def main() -> None:
    async with app.run() as agent_app:
        # Create MCP server (FastMCP) that exposes tools; then add prompts/resources
        mcp_server = create_mcp_server_for_app(agent_app)

        # Register a couple of demo resources
        def _res_readme() -> str:
            return "# Demo Resource\n\nThis is a README resource provided by the reference server."

        def _res_weather(city: str) -> str:
            return f"It is sunny in {city} today!"

        mcp_server.resource("demo://docs/readme")(_res_readme)
        mcp_server.resource("demo://{city}/weather")(_res_weather)

        # Register a simple prompt
        def _prompt_echo(message: str) -> str:
            return f"Prompt: {message}"

        mcp_server.prompt()(_prompt_echo)

        await mcp_server.run_sse_async()


if __name__ == "__main__":
    asyncio.run(main())
