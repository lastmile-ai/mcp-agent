#!/usr/bin/env python3
"""
TokenCounter Example with Custom Watchers

This example demonstrates:
1. Using TokenProgressDisplay for live token tracking
2. Custom watch callbacks for monitoring token usage
3. Comprehensive token usage breakdowns
"""

import asyncio
import os
import time
from datetime import datetime
from typing import Dict, List

from mcp_agent.app import MCPApp
from mcp_agent.core.context import Context
from mcp_agent.agents.agent import Agent
from mcp_agent.workflows.llm.augmented_llm_anthropic import AnthropicAugmentedLLM
from mcp_agent.workflows.llm.augmented_llm_openai import OpenAIAugmentedLLM
from mcp_agent.tracing.token_counter import TokenNode, TokenUsage, TokenSummary
from mcp_agent.logging.token_progress_display import TokenProgressDisplay

app = MCPApp(name="token_counter_example")


class TokenMonitor:
    """Simple token monitor to track LLM calls and high usage."""

    def __init__(self):
        self.llm_calls: List[Dict] = []
        self.high_usage_calls: List[Dict] = []

    async def on_token_update(self, node: TokenNode, usage: TokenUsage):
        """Track token updates for monitoring."""
        # Track LLM calls
        if node.node_type == "llm":
            self.llm_calls.append(
                {
                    "time": datetime.now().strftime("%H:%M:%S"),
                    "node": node.name,
                    "model": node.usage.model_name or "unknown",
                    "total": usage.total_tokens,
                    "input": usage.input_tokens,
                    "output": usage.output_tokens,
                }
            )

            # Track high usage
            if usage.total_tokens > 1000:
                self.high_usage_calls.append(
                    {
                        "time": datetime.now().strftime("%H:%M:%S"),
                        "node": f"{node.name} ({node.node_type})",
                        "tokens": usage.total_tokens,
                    }
                )
                print(
                    f"\n⚠️  High token usage: {node.name} used {usage.total_tokens:,} tokens!"
                )


def display_token_usage(usage: TokenUsage, label: str = "Token Usage"):
    """Display token usage in a formatted way."""
    print(f"\n{label}:")
    print(f"  Total tokens: {usage.total_tokens:,}")
    print(f"  Input tokens: {usage.input_tokens:,}")
    print(f"  Output tokens: {usage.output_tokens:,}")


async def display_token_summary(context: Context):
    """Display comprehensive token usage summary."""
    if not context.token_counter:
        print("\nNo token counter available")
        return

    summary: TokenSummary = await context.token_counter.get_summary()

    print("\n" + "=" * 60)
    print("TOKEN USAGE SUMMARY")
    print("=" * 60)

    # Total usage
    display_token_usage(summary.usage, label="Total Usage")
    print(f"  Total cost: ${summary.cost:.4f}")

    # Breakdown by model
    if summary.model_usage:
        print("\nBreakdown by Model:")
        for model_key, data in summary.model_usage.items():
            print(f"\n  {model_key}:")
            print(
                f"    Tokens: {data.usage.total_tokens:,} (input: {data.usage.input_tokens:,}, output: {data.usage.output_tokens:,})"
            )
            print(f"    Cost: ${data.cost:.4f}")

    # Breakdown by agent
    agents_breakdown = await context.token_counter.get_agents_breakdown()
    if agents_breakdown:
        print("\nBreakdown by Agent:")
        for agent_name, usage in agents_breakdown.items():
            print(f"\n  {agent_name}:")
            print(f"    Total tokens: {usage.total_tokens:,}")
            print(f"    Input tokens: {usage.input_tokens:,}")
            print(f"    Output tokens: {usage.output_tokens:,}")

    print("\n" + "=" * 60)


async def display_node_tree(
    node: TokenNode, indent: str = "", is_last: bool = True, context: Context = None
):
    """Display token usage tree similar to workflow_orchestrator_worker example."""
    # Get usage info
    usage = node.aggregate_usage()

    # Calculate cost if context is available
    cost_str = ""
    if context and context.token_counter:
        cost = await context.token_counter.get_node_cost(node.name, node.node_type)
        if cost > 0:
            cost_str = f" (${cost:.4f})"

    # Choose connector
    connector = "└─ " if is_last else "├─ "

    # Display node info
    print(f"{indent}{connector}{node.name} [{node.node_type}]")
    print(
        f"{indent}{'    ' if is_last else '│   '}├─ Total: {usage.total_tokens:,} tokens{cost_str}"
    )
    print(f"{indent}{'    ' if is_last else '│   '}├─ Input: {usage.input_tokens:,}")
    print(f"{indent}{'    ' if is_last else '│   '}└─ Output: {usage.output_tokens:,}")

    # If node has model info, show it
    if node.usage.model_name:
        model_str = node.usage.model_name
        if node.usage.model_info and node.usage.model_info.provider:
            model_str += f" ({node.usage.model_info.provider})"
        print(f"{indent}{'    ' if is_last else '│   '}   Model: {model_str}")

    # Process children
    if node.children:
        print(f"{indent}{'    ' if is_last else '│   '}")
        child_indent = indent + ("    " if is_last else "│   ")
        for i, child in enumerate(node.children):
            await display_node_tree(
                child, child_indent, i == len(node.children) - 1, context
            )


async def example_with_token_monitoring():
    """Run example with token monitoring."""
    async with app.run() as agent_app:
        context = agent_app.context
        token_counter = context.token_counter

        # Create token monitor
        monitor = TokenMonitor()

        # Create token progress display
        with TokenProgressDisplay(token_counter) as _progress:
            print("\n✨ Token Counter Example with Live Monitoring")
            print("Watch the token usage update in real-time!\n")

            # Register custom watch for monitoring
            watch_id = await token_counter.watch(
                callback=monitor.on_token_update,
                threshold=1,  # Track all updates
            )

            # Configure filesystem server
            if "filesystem" in context.config.mcp.servers:
                context.config.mcp.servers["filesystem"].args.extend([os.getcwd()])

            # Create agents
            finder_agent = Agent(
                name="finder",
                instruction="""You are an agent with access to the filesystem. 
                Your job is to find and read files as requested.""",
                server_names=["filesystem"],
            )

            analyzer_agent = Agent(
                name="analyzer",
                instruction="""You analyze and summarize information.""",
                server_names=[],
            )

            # Run tasks with different agents and models
            async with finder_agent:
                print("📁 Task 1: File system query (OpenAI)")
                llm = await finder_agent.attach_llm(OpenAIAugmentedLLM)
                result = await llm.generate_str(
                    "List the Python files in the current directory."
                )
                print(f"Found: {result[:100]}...\n")

                await asyncio.sleep(0.5)

            async with analyzer_agent:
                print("🔍 Task 2: Analysis (Anthropic)")
                llm = await analyzer_agent.attach_llm(AnthropicAugmentedLLM)

                # First query
                result = await llm.generate_str(
                    "What are the key components of a token counting system for LLMs?"
                )
                print(f"Components: {result[:100]}...\n")

                await asyncio.sleep(0.5)

                # Follow-up query
                print("📝 Task 3: Follow-up question")
                result = await llm.generate_str("Summarize that in 3 bullet points.")
                print(f"Summary: {result[:100]}...\n")

            # Cleanup watch
            await token_counter.unwatch(watch_id)

            # Show custom monitoring results
            if monitor.llm_calls:
                print("\n📊 LLM Call Summary:")
                for call in monitor.llm_calls:
                    print(
                        f"  {call['time']} - {call['model']}: {call['total']:,} tokens"
                    )

            if monitor.high_usage_calls:
                print(f"\n⚠️  High Usage Alerts: {len(monitor.high_usage_calls)} calls")

        # Display comprehensive summaries
        await display_token_summary(context)

        # Display token tree
        print("\n" + "=" * 60)
        print("TOKEN USAGE TREE")
        print("=" * 60)
        print()

        if hasattr(token_counter, "_root") and token_counter._root:
            await display_node_tree(token_counter._root, context=context)


if __name__ == "__main__":
    start = time.time()
    asyncio.run(example_with_token_monitoring())
    end = time.time()

    print(f"\nTotal run time: {end - start:.2f}s")
