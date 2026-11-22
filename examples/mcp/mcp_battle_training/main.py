import asyncio
import os
import time

from mcp_agent.app import MCPApp
from mcp_agent.agents.agent import Agent
from mcp_agent.workflows.llm.augmented_llm_openai import OpenAIAugmentedLLM


# Settings can either be specified programmatically,
# or loaded from mcp_agent.config.yaml/mcp_agent.secrets.yaml
app = MCPApp(name="mcp_battle_training")

# The operator's own bots on battle.training, used as read-only example
# subjects. Anyone can substitute any public bot name here.
EXAMPLE_BOTS = ["delynn-prime", "delynn-pyong"]


def _text(result) -> str:
    """Flatten a CallToolResult's content blocks into plain text."""
    parts = []
    for block in result.content or []:
        parts.append(getattr(block, "text", str(block)))
    return "\n".join(parts)


def _log_result(logger, label: str, result) -> bool:
    """Log a tool result, treating isError results as failures, not data.

    The aggregator returns failed tool calls as a CallToolResult with
    isError=True instead of raising, so check the flag before treating
    the content as standings.
    """
    if getattr(result, "isError", False):
        logger.error(f"{label} FAILED:", data={"result": _text(result)})
        return False
    logger.info(label, data={"result": _text(result)})
    return True


async def example_usage():
    async with app.run() as agent_app:
        logger = agent_app.logger
        context = agent_app.context

        logger.info("Current config:", data=context.config.model_dump())

        agent = Agent(
            name="battle-training-scout",
            instruction="""You are a scouting agent for battle.training, an arena
            where AI agents fight rated bot battles. You read the public
            ladders and bot standings through the battle.training MCP server
            and summarize what you find. You never modify anything.""",
            server_names=["battle_training"],
        )

        async with agent:
            logger.info("battle-training-scout: Connected, calling list_tools...")
            tools = await agent.list_tools()
            tool_names = [t.name for t in tools.tools]
            logger.info("Tools available:", data={"tools": tool_names})

            # Read-only public calls — no battle.training account needed.
            ladders = await agent.call_tool("list_ladders", {})
            _log_result(logger, "Open ladders:", ladders)

            ladder = await agent.call_tool("get_ladder", {})
            _log_result(logger, "Default ladder standings:", ladder)

            for bot_name in EXAMPLE_BOTS:
                bot = await agent.call_tool("get_bot", {"name": bot_name})
                _log_result(logger, f"Bot {bot_name}:", bot)

            # Optional: let an LLM summarize the standings. Skipped cleanly
            # when no OpenAI API key is configured.
            if os.getenv("OPENAI_API_KEY"):
                llm = await agent.attach_llm(OpenAIAugmentedLLM)
                summary = await llm.generate_str(
                    message=(
                        "Using the battle_training tools, read the current "
                        "ladder standings and summarize the top of the table "
                        f"and where the bots {', '.join(EXAMPLE_BOTS)} sit."
                    )
                )
                logger.info("LLM summary:", data={"summary": summary})
            else:
                logger.info(
                    "OPENAI_API_KEY not set — skipping the optional LLM "
                    "summary. The direct read-tool calls above are the "
                    "tested path of this example."
                )


if __name__ == "__main__":
    start = time.time()
    asyncio.run(example_usage())
    end = time.time()
    t = end - start

    print(f"Total run time: {t:.2f}s")
