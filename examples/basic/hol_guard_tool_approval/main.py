"""Example app wiring HOL Guard into AugmentedLLM.pre_tool_call.

Run this example after installing HOL Guard and setting OpenAI credentials. The
important part is the LLM class in hol_guard_llm.py: it asks HOL Guard about the
pending MCP tool call and returns False unless Guard explicitly allows it.
"""

from hol_guard_llm import HolGuardedOpenAIAugmentedLLM

from mcp_agent.agents.agent import Agent
from mcp_agent.app import MCPApp

app = MCPApp(name="hol_guard_tool_approval")


async def main() -> None:
    async with app.run() as mcp_app:
        agent = Agent(
            name="guarded_assistant",
            instruction="Use tools only when HOL Guard approves the exact call.",
            server_names=["fetch"],
        )
        await agent.initialize()
        llm = await agent.attach_llm(HolGuardedOpenAIAugmentedLLM)
        result = await llm.generate_str("Fetch https://modelcontextprotocol.io/")
        mcp_app.logger.info(result)


if __name__ == "__main__":
    app.run_main(main)
