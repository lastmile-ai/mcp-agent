import asyncio

from mcp_agent.app import MCPApp
from mcp_agent.workflows.factory import create_router_llm


async def main():
    async with MCPApp(name="auto_subagents_demo").run() as agent_app:
        context = agent_app.context

        # Ensure filesystem server points to current repo for demo purposes
        if "filesystem" in context.config.mcp.servers:
            context.config.mcp.servers["filesystem"].args.extend(["."])

        loaded = getattr(context, "loaded_subagents", []) or []
        print(f"Discovered {len(loaded)} subagents from configured search paths")
        if not loaded:
            print(
                "Hint: create subagents in .claude/agents or .mcp-agent/agents (or home equivalents)"
            )
            return

        router = await create_router_llm(
            server_names=["filesystem", "fetch"],
            agents=loaded,
            provider="openai",
            context=context,
        )

        res = await router.generate_str("Find and summarize the main README")
        print("Routing result:", res)


if __name__ == "__main__":
    asyncio.run(main())
