import asyncio
from pathlib import Path

from mcp_agent.core.context import Context

from mcp_agent.app import MCPApp
from mcp_agent.workflows.factory import (
    create_router_llm,
    load_agent_specs_from_file,
)

app = MCPApp(name="factory_demo", description="Demo of agent factory with LLM routing")


@app.async_tool()
async def route_prompt(
    prompt: str = "Find the README and summarize it", app_ctx: Context | None = None
) -> str:
    """Route a prompt to the appropriate agent using an LLMRouter."""
    context = app_ctx or app.context

    agents_path = Path(__file__).resolve().parent / "agents.yaml"
    specs = load_agent_specs_from_file(str(agents_path), context=context)

    router = await create_router_llm(
        server_names=["filesystem", "fetch"],
        agents=specs,
        provider="openai",
        context=context,
    )

    return await router.generate_str(prompt)


async def main():
    async with app.run() as agent_app:
        result = await route_prompt(
            prompt="Find the README and summarize it", app_ctx=agent_app.context
        )
        print("Routing result:", result)


if __name__ == "__main__":
    asyncio.run(main())
