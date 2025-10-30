"""Temporal cloud agent factory example with custom workflow tasks."""

from __future__ import annotations

import asyncio
from pathlib import Path

from mcp_agent.core.context import Context

from mcp_agent.app import MCPApp
from mcp_agent.server.app_server import create_mcp_server_for_app
from mcp_agent.workflows.factory import (
    create_router_llm,
    load_agent_specs_from_file,
)

try:
    from .custom_tasks import knowledge_base_lookup_task
except ImportError:  # pragma: no cover - executed when run as a script
    from custom_tasks import knowledge_base_lookup_task

app = MCPApp(
    name="cloud_agent_factory",
    description="Temporal agent factory demo that uses custom workflow tasks",
)


@app.async_tool()
async def route_customer_request(
    prompt: str = "A customer is asking about our pricing and security posture.",
    context_hits: int = 3,
    app_ctx: Context | None = None,
) -> str:
    """Route customer-facing questions and seed the LLM with KB context."""
    context = app_ctx or app.context

    kb_snippets = await context.executor.execute(
        knowledge_base_lookup_task,
        {"query": prompt, "limit": context_hits},
    )
    if isinstance(kb_snippets, BaseException):
        raise kb_snippets

    kb_context = "\n\n".join(kb_snippets) if kb_snippets else "No knowledge-base hits."
    agents_path = Path(__file__).resolve().parent / "agents.yaml"
    specs = load_agent_specs_from_file(str(agents_path), context=context)

    router = await create_router_llm(
        server_names=["filesystem", "fetch"],
        agents=specs,
        provider="openai",
        context=context,
    )

    enriched_prompt = (
        "You are triaging a customer request.\n"
        f"Customer question:\n{prompt}\n\n"
        f"Knowledge-base snippets:\n{kb_context}\n\n"
        "Compose a helpful, empathetic reply that references the most relevant details."
    )
    return await router.generate_str(enriched_prompt)


# async def main():
#     async with app.run() as agent_app:
#         result = await route_customer_request(app_ctx=agent_app.context)
#         print("Routing result:", result)


async def main():
    async with app.run() as agent_app:
        mcp_server = create_mcp_server_for_app(agent_app)
        await mcp_server.run_sse_async()


if __name__ == "__main__":
    asyncio.run(main())
