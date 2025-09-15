"""
Welcome to mcp-agent!
This
Canonical MCP-Agent example for new projects.

This script showcases:
  - Setting up a basic Agent that uses the fetch and filesystem MCP servers
  - @app.tool and @app.async_tool decorators to define long-running tools
  - Advanced MCP features: Notifications, sampling, and elicitation
"""

from __future__ import annotations

from typing import Optional, Literal
import os

from mcp.server.fastmcp import Context as MCPContext
from mcp.types import ElicitRequestedSchema, TextContent, CreateMessageResult

from mcp_agent.app import MCPApp
from mcp_agent.agents.agent import Agent
from mcp_agent.agents.agent_spec import AgentSpec
from mcp_agent.core.context import Context as AppContext
from mcp_agent.workflows.factory import create_llm
from mcp_agent.workflows.llm.augmented_llm import RequestParams as LLMRequestParams
from mcp_agent.workflows.llm.llm_selector import ModelPreferences

# If you want to use a different LLM provider, you can import the appropriate AugmentedLLM
#
from mcp_agent.workflows.llm.augmented_llm_openai import OpenAIAugmentedLLM

# Create the MCP App. Configuration is read from mcp_agent.config.yaml/secrets.yaml.
app = MCPApp(name="hello_world", description="Hello world mcp-agent application")


# 1) Agent behavior (first): demonstrate an Agent using MCP servers + LLM
@app.tool(name="finder_tool")
async def finder_tool(request: str, app_ctx: Optional[AppContext] = None) -> str:
    """
    Create an Agent with access to MCP servers (fetch + filesystem), attach an LLM,
    and handle the user's request.
    """
    _app = app_ctx.app if app_ctx else app
    ctx = _app.context

    # Ensure filesystem server can read current working directory (dev-friendly)
    try:
        if "filesystem" in ctx.config.mcp.servers:
            ctx.config.mcp.servers["filesystem"].args.extend([os.getcwd()])
    except Exception:
        pass

    agent = Agent(
        name="finder",
        instruction=(
            "You are a helpful assistant. Use MCP servers to fetch and read files,"
            " then answer the request concisely."
        ),
        server_names=["fetch", "filesystem"],
    )

    async with agent:
        llm = await agent.attach_llm(OpenAIAugmentedLLM)
        result = await llm.generate_str(message=request)
        return result


# 2) Agent catalog: list agents defined in config (agents.definitions)
@app.tool(name="agent_catalog")
def agent_catalog(app_ctx: Optional[AppContext] = None) -> str:
    """List agent names defined under config.agents.definitions."""
    _app = app_ctx.app if app_ctx else app
    defs: list[AgentSpec] = (
        getattr(getattr(_app.context.config, "agents", None), "definitions", []) or []
    )
    names = [getattr(d, "name", "") for d in defs if getattr(d, "name", None)]
    return ", ".join(names) if names else "(no agents defined in config)"


# 3) Run a configured agent by name (from config.agents.definitions)
@app.tool(name="run_agent")
async def run_agent(
    agent_name: str,
    prompt: str,
    app_ctx: Optional[AppContext] = None,
) -> str:
    """
    Instantiate an Agent from config.agents.definitions by name and run an LLM call.
    """
    _app = app_ctx.app if app_ctx else app
    defs: list[AgentSpec] = (
        getattr(getattr(_app.context.config, "agents", None), "definitions", []) or []
    )
    spec = next((d for d in defs if getattr(d, "name", None) == agent_name), None)
    if spec is None:
        return f"agent '{agent_name}' not found"

    agent = Agent(
        name=spec.name,
        instruction=spec.instruction,
        server_names=spec.server_names or [],
        functions=getattr(spec, "functions", []),
        context=_app.context,
    )
    async with agent:
        llm = await agent.attach_llm(OpenAIAugmentedLLM)
        return await llm.generate_str(message=prompt)


# 4) Minimal tool: synchronous, simple types
@app.tool(name="greet")
def greet(name: str, app_ctx: Optional[AppContext] = None) -> str:
    """Return a friendly greeting and log it upstream."""
    _app = app_ctx.app if app_ctx else app
    _app.logger.info("greet called", data={"name": name})
    return f"Hello, {name}!"


# 5) Notify: demonstrate server-side logging notifications
@app.tool(name="notify")
def notify(
    message: str,
    level: Literal["debug", "info", "warning", "error"] = "info",
    app_ctx: Optional[AppContext] = None,
    mcp_ctx: Optional[MCPContext] = None,
) -> str:
    """
    Send a non-logging notification via the app logger (forwarded upstream).
    Tools get access to both the MCPApp Context (app_ctx) and FastMCP Context (mcp_ctx).
    """
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


# 6) Elicit: prompt the user for confirmation (demonstrates elicitation)
@app.tool(name="confirm_action")
async def confirm_action(
    action: str,
    app_ctx: Optional[AppContext] = None,
    ctx: Optional[MCPContext] = None,
) -> str:
    """
    Ask the user to confirm an action. When invoked from an MCP client UI, a prompt is shown.
    Falls back to the app's elicitation handler if no upstream client is attached.
    """
    _app = app_ctx.app if app_ctx else app
    upstream = getattr(_app.context, "upstream_session", None)
    schema: ElicitRequestedSchema = {
        "type": "object",
        "title": "Confirmation",
        "properties": {"confirm": {"type": "boolean", "title": "Confirm"}},
        "required": ["confirm"],
    }
    # Prefer upstream elicitation when available
    if upstream is not None:
        result = await upstream.elicit(
            message=f"Do you want to {action}?", requestedSchema=schema
        )
        accepted = getattr(result, "action", "") in ("accept", "accepted")
        return f"Action '{action}' {'confirmed' if accepted else 'declined'} by user"

    # Fallback: no upstream client. If an elicitation handler is configured, use it.
    if _app.context.elicitation_handler:
        resp = await _app.context.elicitation_handler(
            {"message": f"Do you want to {action}?", "requestedSchema": schema}
        )
        accepted = getattr(resp, "action", "") in ("accept", "accepted")
        return f"Action '{action}' {'confirmed' if accepted else 'declined'}"

    # Last resort: assume accepted
    return f"Action '{action}' confirmed by default"


# 7) Sampling: call an LLM to generate a short text
@app.tool(name="sample_haiku")
async def sample_haiku(topic: str, app_ctx: Optional[AppContext] = None) -> str:
    """
    Generate a tiny poem using the configured LLM. Model and keys come from config/secrets.
    """
    _app = app_ctx.app if app_ctx else app
    # Create a simple LLM using current app context (settings and servers)
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
    text = await llm.generate_str(message=f"Haiku about {topic}", request_params=req)
    return text


# 8) Async tool: demonstrates @app.async_tool (runs asynchronously)
@app.async_tool(name="reverse_async")
async def reverse_async(text: str) -> str:
    """Reverse a string asynchronously (example async tool)."""
    return text[::-1]


# 6) Router demo (agent factory): route query to specialized agents defined in agents.yaml
@app.tool(name="route_demo")
async def route_demo(query: str, app_ctx: Optional[AppContext] = None) -> str:
    """
    Use the agent factory to load agent specs from agents.yaml and route the query
    to the best agent using an LLM router.
    """
    from pathlib import Path
    from mcp_agent.workflows.factory import (
        load_agent_specs_from_file,
        create_router_llm,
    )

    _app = app_ctx.app if app_ctx else app
    ctx = _app.context
    specs = load_agent_specs_from_file(str(Path("agents.yaml").resolve()), context=ctx)
    router = await create_router_llm(
        server_names=["filesystem", "fetch"],
        agents=specs,
        provider="openai",
        context=ctx,
    )
    res = await router.generate_str(query)
    return res


if __name__ == "__main__":
    # Optional: run a quick sanity check when executed directly
    import asyncio

    async def _smoke():
        async with app.run() as running:
            running.logger.info("Example app started")
            print(
                await finder_tool(
                    "List files in the current directory", app_ctx=running.context
                )
            )
            print("Agents:", await agent_catalog(app_ctx=running.context))
            print(
                await run_agent(
                    "filesystem_helper",
                    "Summarize README if present",
                    app_ctx=running.context,
                )
            )
            print(await greet("World", app_ctx=running.context))
            print(await sample_haiku("flowers", app_ctx=running.context))

    asyncio.run(_smoke())
