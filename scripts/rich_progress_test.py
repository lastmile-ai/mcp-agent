#!/usr/bin/env python3
"""Test script for demonstrating the Rich progress display."""

import asyncio
import random
from mcp_agent.logging.events import Event
from mcp_agent.logging.listeners import ProgressListener
from rich import print


async def generate_test_events():
    """Generate synthetic progress events for testing."""
    # Simulate an MCP session with multiple activities
    mcp_names = ["Assistant-1", "Helper-2", "Agent-3"]
    models = ["gpt-4", "claude-2", "mistral"]
    tools = [
        "developer__shell",
        "platform__read_resource",
        "computercontroller__web_search",
    ]

    for mcp_name in mcp_names:
        # Starting up
        yield Event(
            namespace="mcp_connection_manager",
            type="info",
            message=f"{mcp_name}: Initializing server session",
            data={},
        )
        # Simulate some other console output
        print(f"Debug: Connection established for {mcp_name}")
        await asyncio.sleep(0.5)

        # Initialized
        yield Event(
            namespace="mcp_connection_manager",
            type="info",
            message=f"{mcp_name}: Session initialized",
            data={},
        )
        await asyncio.sleep(0.5)

        # Simulate some chat turns
        for turn in range(1, 4):
            model = random.choice(models)

            # Start chat turn
            yield Event(
                namespace="mcp_agent.workflow.llm.augmented_llm_openai.myagent",
                type="info",
                message=f"Calling {model}",
                data={"model": model, "chat_turn": turn},
            )
            await asyncio.sleep(1)

            # Maybe call a tool
            if random.random() < 0.7:
                tool = random.choice(tools)
                print(f"Debug: Executing tool {tool}")  # More debug output
                yield Event(
                    namespace="mcp_aggregator",
                    type="info",
                    message=f"Requesting tool call '{tool}'",
                    data={},
                )
                await asyncio.sleep(0.8)

            # Finish chat turn
            yield Event(
                namespace="augmented_llm",
                type="info",
                message="Finished processing response",
                data={"model": model},
            )
            await asyncio.sleep(0.5)

        # Shutdown
        print(f"Debug: Shutting down {mcp_name}")  # More debug output
        yield Event(
            namespace="mcp_connection_manager",
            type="info",
            message=f"{mcp_name}: _lifecycle_task is exiting",
            data={},
        )
        await asyncio.sleep(1)


async def main():
    """Run the progress display test."""
    # Set up the progress listener
    listener = ProgressListener()
    await listener.start()

    try:
        async for event in generate_test_events():
            await listener.handle_event(event)
    except KeyboardInterrupt:
        print("\nTest interrupted!")
    finally:
        await listener.stop()


if __name__ == "__main__":
    asyncio.run(main())
