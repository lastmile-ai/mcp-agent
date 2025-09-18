"""
Sampling Server (asyncio)

Demonstrates a minimal LLM sampling tool.

Run:
  uv run server.py
"""

from __future__ import annotations

import asyncio
from typing import Optional

from mcp_agent.app import MCPApp
from mcp_agent.core.context import Context as AppContext
from mcp_agent.server.app_server import create_mcp_server_for_app
from mcp_agent.workflows.factory import create_llm
from mcp_agent.workflows.llm.augmented_llm import RequestParams as LLMRequestParams
from mcp_agent.workflows.llm.llm_selector import ModelPreferences


app = MCPApp(
    name="sampling_server",
    description="Minimal server showing LLM sampling",
    human_input_callback=None,
)


@app.tool(name="sample_haiku")
async def sample_haiku(
    topic: str,
    temperature: float | None = 0.7,
    app_ctx: Optional[AppContext] = None,
) -> str:
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
        temperature=temperature,
        use_history=False,
        max_iterations=1,
    )
    return await llm.generate_str(message=f"Haiku about {topic}", request_params=req)


async def main() -> None:
    async with app.run() as agent_app:
        mcp_server = create_mcp_server_for_app(agent_app)
        await mcp_server.run_sse_async()


if __name__ == "__main__":
    asyncio.run(main())
