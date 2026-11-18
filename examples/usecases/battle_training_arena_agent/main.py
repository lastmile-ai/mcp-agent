"""Example: Connect mcp-agent to the battle.training Streamable HTTP MCP server."""

import argparse
import asyncio
import json

from mcp_agent.agents.agent import Agent
from mcp_agent.app import MCPApp
from mcp_agent.workflows.llm.augmented_llm_openai import OpenAIAugmentedLLM

app = MCPApp(name="battle_training_arena_agent")


def extract_text_payload(result: object) -> str:
    """Flatten MCP CallToolResult content blocks into a single text string."""
    content = getattr(result, "content", None) or []
    parts = [getattr(item, "text", "") for item in content if getattr(item, "text", None)]
    return "\n".join(parts)


async def inspect_arena(bot_name: str, use_llm: bool) -> None:
    """Connect to battle.training over Streamable HTTP MCP and inspect ladder state."""
    async with app.run() as agent_app:
        logger = agent_app.logger
        arena_agent = Agent(
            name="battle-training-analyst",
            instruction=(
                "You inspect battle.training ladders, rules, and bot match records "
                "using the battle_training MCP server tools."
            ),
            server_names=["battle_training"],
        )

        async with arena_agent:
            tools_res = await arena_agent.list_tools()
            tool_names = [t.name for t in getattr(tools_res, "tools", [])]
            logger.info("Connected to battle.training MCP", data={"tools": len(tool_names)})

            ladders_raw = await arena_agent.call_tool("list_ladders", {})
            ladders_text = extract_text_payload(ladders_raw)
            ladders_data = json.loads(ladders_text) if ladders_text else {}
            ladders = ladders_data.get("ladders", [])
            logger.info("Active ladders", data={"count": len(ladders)})

            bot_raw = await arena_agent.call_tool("get_bot", {"name": bot_name})
            bot_text = extract_text_payload(bot_raw)
            logger.info("Bot snapshot loaded", data={"bot": bot_name, "bytes": len(bot_text)})

            if use_llm:
                llm = await arena_agent.attach_llm(OpenAIAugmentedLLM)
                summary = await llm.generate_str(
                    message=(
                        f"Call get_bot for '{bot_name}' and list_matches for '{bot_name}' "
                        "(limit 5). Summarize its current rating, active version, and recent match outcomes."
                    )
                )
                print("\n=== LLM Arena Summary ===\n")
                print(summary)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="battle.training MCP agent example")
    parser.add_argument("--bot", default="nmore-vanguard", help="Target bot name on battle.training")
    parser.add_argument("--llm", action="store_true", help="Run LLM analysis via OpenAIAugmentedLLM")
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    asyncio.run(inspect_arena(bot_name=args.bot, use_llm=args.llm))
