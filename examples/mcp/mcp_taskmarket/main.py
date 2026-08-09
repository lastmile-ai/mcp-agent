"""
Example: TaskMarket MCP Server with mcp-agent

This example shows how to use the TaskMarket MCP server as an
approver-gated delegation surface inside an mcp-agent workflow.

The agent can:
  1. Browse open TaskMarket tasks (read tools, no wallet needed).
  2. Fetch task details and submissions.
  3. Check wallet balance and address.
  4. Claim, submit work, submit proofs, or create tasks -- but only
     after explicit operator approval (approve=true).

Setup:
  1. Install the taskmarket CLI globally:
     npm install -g @lucid-agents/taskmarket@latest

  2. Initialise your wallet (one-time):
     taskmarket init

  3. Run the MCP server in one terminal:
     python server.py

  4. Run this agent in another terminal:
     uv run main.py
"""

import asyncio
import json

from dotenv import load_dotenv
from rich import print
from mcp.types import CallToolResult
from mcp_agent.agents.agent import Agent
from mcp_agent.app import MCPApp

load_dotenv()


async def main():
    app: MCPApp = MCPApp(name="taskmarket-example")
    async with app.run():
        print("[bold cyan]MCP App initialized.[/bold cyan]")
        print("Connecting to the TaskMarket MCP server...\n")

        agent: Agent = Agent(
            name="taskmarket_agent",
            instruction=(
                "You are an autonomous agent that can interact with the TaskMarket "
                "on-chain task marketplace on Base. You have read tools to browse "
                "open tasks, fetch details, list submissions, check wallet balance, "
                "and write tools to claim, submit, prove, or create tasks. All "
                "write operations require explicit approval via the `approve` "
                "parameter. Never spend funds without user authorization. "
                "Use the taskmarket_* tools to help the user find and evaluate "
                "available work."
            ),
            server_names=["taskmarket"],
        )

        async with agent:
            # List available tools
            tools = await agent.list_tools()
            print(f"[green]Available tools: {len(tools)}[/green]")
            for name in tools:
                print(f"  - {name}")

            print("\n[bold]Browsing open tasks...[/bold]")

            # Browse open tasks
            result: CallToolResult = await agent.call_tool(
                "taskmarket_list_open_tasks",
                arguments={"limit": 5},
            )
            output = result.content[0].text
            data = json.loads(output)
            tasks = data.get("tasks", [])

            for t in tasks:
                print(f"\n  [yellow]{t['reward_usdc']:.4f} USDC[/yellow] | {t['mode']} | {t['status']}")
                print(f"  Expires: {t['expiry_time']}")
                print(f"  Submissions: {t['submission_count']} | Net: {t['net_reward_usdc']:.4f} USDC")
                desc = t.get("title", "")[:120]
                print(f"  {desc}")

            # Check wallet
            print("\n[bold]Checking wallet...[/bold]")
            addr_result = await agent.call_tool("taskmarket_wallet_address")
            print(f"  Address: {addr_result.content[0].text}")

            bal_result = await agent.call_tool("taskmarket_wallet_balance")
            bal_data = json.loads(bal_result.content[0].text)
            print(f"  Balance: {bal_data.get('data', {}).get('balanceUsdc', 'unknown')} USDC")


if __name__ == "__main__":
    asyncio.run(main())
