"""
Lore Context Memory-Enhanced Research Agent

Demonstrates how to use Lore Context as a persistent memory backend for
mcp-agent.  The agent stores research findings in Lore across multiple
sessions, then recalls past context when answering new questions.

This fills the cross-session memory gap that mcp-agent's built-in
SimpleMemory cannot address — memories survive process restarts and
are semantically searchable.
"""

import asyncio
import time

from mcp_agent.app import MCPApp
from mcp_agent.agents.agent import Agent
from mcp_agent.workflows.llm.augmented_llm_openai import OpenAIAugmentedLLM
from mcp_agent.logging.logger import LoggingConfig
from rich import print

app = MCPApp(name="mcp_lore_memory_agent")

# ---------------------------------------------------------------------------
# Simulated multi-session research flow
# ---------------------------------------------------------------------------

RESEARCH_TOPICS = [
    {
        "session": "Session 1 — Initial Research",
        "query": (
            "Research the current state of quantum computing in 2026. "
            "Find key milestones, leading companies, and recent breakthroughs. "
            "Store your findings in Lore memory so we can build on them later."
        ),
    },
    {
        "session": "Session 2 — Follow-up Research",
        "query": (
            "Now research quantum error correction advances in 2025-2026. "
            "Before starting, check Lore memory for any prior findings on "
            "quantum computing so you can build on existing context. "
            "Store the new findings alongside the previous ones."
        ),
    },
    {
        "session": "Session 3 — Synthesis",
        "query": (
            "Using all the knowledge stored in Lore memory about quantum "
            "computing and quantum error correction, produce a brief "
            "synthesis report. Search Lore for all related memories first, "
            "then write a coherent summary."
        ),
    },
]


async def run_research_session(agent: Agent, session_info: dict) -> str:
    """Run a single research session with the agent."""
    print(f"\n{'='*60}")
    print(f"  {session_info['session']}")
    print(f"{'='*60}\n")

    llm = await agent.attach_llm(OpenAIAugmentedLLM)
    result = await llm.generate_str(session_info["query"])
    print(result)
    return result


async def example_usage():
    async with app.run() as agent_app:
        context = agent_app.context

        lore_agent = Agent(
            name="lore_research_agent",
            instruction="""You are a research assistant with persistent memory
            powered by Lore Context.  You have access to the following Lore
            tools:

            - lore_memory_write  : Save important findings to long-term memory
            - lore_memory_search : Semantically search past memories
            - lore_context_query : Get rich context from memory + other sources
            - lore_memory_list   : Browse stored memories
            - lore_memory_export : Export memories as JSON or Markdown

            ALWAYS store important research findings using lore_memory_write so
            they persist across sessions.  When starting new research, FIRST
            search Lore memory for relevant prior context using
            lore_memory_search or lore_context_query before doing fresh
            research.  This builds cumulative knowledge over time.""",
            server_names=["lore"],
        )

        try:
            async with lore_agent:
                for topic in RESEARCH_TOPICS:
                    await run_research_session(lore_agent, topic)

                # Final: export all stored memories
                print(f"\n{'='*60}")
                print("  Exporting all Lore memories …")
                print(f"{'='*60}\n")

                llm = await lore_agent.attach_llm(OpenAIAugmentedLLM)
                export = await llm.generate_str(
                    "List all memories you have stored in Lore. "
                    "Use lore_memory_list or lore_memory_export to show them."
                )
                print(export)

        finally:
            await lore_agent.close()

    await LoggingConfig.shutdown()


if __name__ == "__main__":
    start = time.time()
    try:
        asyncio.run(example_usage())
    except KeyboardInterrupt:
        print("\nReceived keyboard interrupt, shutting down gracefully …")
    except Exception as e:
        print(f"Error during execution: {e}")
        raise
    finally:
        end = time.time()
        print(f"Total run time: {end - start:.2f}s")
