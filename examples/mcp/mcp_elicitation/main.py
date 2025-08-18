import asyncio
import time

from mcp_agent.app import MCPApp
from mcp_agent.agents.agent import Agent
from mcp_agent.human_input.handler import console_input_callback
from mcp_agent.elicitation.handler import console_elicitation_callback
from mcp_agent.workflows.llm.augmented_llm_openai import OpenAIAugmentedLLM

# Elicitation callback is required to handle elicitation requests
app = MCPApp(
    name="mcp_basic_agent",
    human_input_callback=console_input_callback,  # Optional
    elicitation_callback=console_elicitation_callback,
)


async def example_usage():
    async with app.run() as agent_app:
        logger = agent_app.logger

        # --- Example: Using the demo_server MCP server ---
        agent = Agent(
            name="agent",
            instruction="You are a cafe reservation assistant",
            server_names=["demo_server"],
        )

        async with agent:
            llm = await agent.attach_llm(OpenAIAugmentedLLM)
            res = await llm.generate_str("Can you book a table for 2 on 21 Jun at 5pm?")
            logger.info(f"Result: {res}")
            print(f"Result: {res}")


if __name__ == "__main__":
    start = time.time()
    asyncio.run(example_usage())
    end = time.time()
    t = end - start

    print(f"Total run time: {t:.2f}s")
