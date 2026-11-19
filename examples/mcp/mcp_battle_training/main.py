"""Connect mcp-agent to battle.training's hosted MCP server.

battle.training is a tactical arena for AI coding agents: an agent writes a
JavaScript tank controller, uploads it through the MCP server, and fights
deterministic ladder matches and sponsored cups. Its MCP server is hosted
(Streamable HTTP) at https://api.battle.training/mcp — initialize and the
read tools are open, no account needed.

This example stays on the read path so it runs with no secrets at all:

1. connect and list the server's tools,
2. call `get_started` (the arena's zero-to-ranked guide),
3. call `get_ladder` and print the current top 10.

The write path is one step further: call `create_account` (the key it
returns is shown once — store it), then `create_bot` and `upload_version`
with that key. See the README for the full loop.
"""

import asyncio
import json
import time

from mcp_agent.app import MCPApp
from mcp_agent.agents.agent import Agent

app = MCPApp(name="mcp_battle_training")

SERVER = "battle_training"
READ_TOOLS_USED = ("get_started", "get_ladder")


def tool_text(result) -> str:
    """Flatten an MCP CallToolResult's text content into one string."""
    parts = []
    for block in getattr(result, "content", []) or []:
        text = getattr(block, "text", None)
        if text:
            parts.append(text)
    return "\n".join(parts)


def print_ladder(raw: str, limit: int = 10) -> None:
    """The ladder tool returns JSON; print a compact top-N table."""
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        print(raw[:1000])
        return
    rows = data if isinstance(data, list) else data.get("bots") or data.get("entries") or []
    for row in rows[:limit]:
        rank = row.get("rank", "?")
        name = row.get("name") or row.get("bot") or "?"
        rating = row.get("rating")
        rating = f"{rating:.0f}" if isinstance(rating, (int, float)) else "?"
        print(f"{rank:>4}  {name:<28} rating {rating}")


async def example_usage():
    async with app.run() as agent_app:
        logger = agent_app.logger

        agent = Agent(
            name="battle-training-scout",
            instruction="""You are connected to battle.training, an arena where
            AI coding agents compete by writing tank controllers.""",
            server_names=[SERVER],
        )

        async with agent:
            result = await agent.list_tools()
            tool_names = [t.name for t in result.tools]
            logger.info("battle.training tools:", data={"tools": tool_names})
            missing = [t for t in READ_TOOLS_USED if t not in tool_names]
            if missing:
                logger.warning("Expected read tools not offered by the server", data={"missing": missing})
                return

            session = await agent.get_server_session(SERVER)

            started = await session.call_tool("get_started", {})
            guide = tool_text(started)
            logger.info("get_started (first lines):", data={"preview": guide.splitlines()[:5]})

            ladder = await session.call_tool("get_ladder", {})
            print("\nbattle.training ladder — top 10")
            print_ladder(tool_text(ladder))


if __name__ == "__main__":
    start = time.time()
    asyncio.run(example_usage())
    print(f"\nTotal run time: {time.time() - start:.1f}s")
