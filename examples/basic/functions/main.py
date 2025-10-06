import asyncio
import time
from typing import Optional

from mcp_agent.core.context import Context
from mcp_agent.app import MCPApp
from mcp_agent.agents.agent import Agent
from mcp_agent.workflows.llm.augmented_llm_openai import OpenAIAugmentedLLM


def add_numbers(a: int, b: int) -> int:
    """
    Adds two numbers.
    """
    print(f"Math expert is adding {a} and {b}")
    return a + b


def multiply_numbers(a: int, b: int) -> int:
    """
    Multiplies two numbers.
    """
    print(f"Math expert is multiplying {a} and {b}")
    return a * b


app = MCPApp(name="mcp_agent_using_functions")


@app.async_tool
async def calculate(expr: str, app_ctx: Optional[Context] = None) -> str:
    logger = app_ctx.app.logger

    math_agent = Agent(
        name="math_agent",
        instruction="""You are an expert in mathematics with access to some functions
        to perform correct calculations. 
        Your job is to identify the closest match to a user's request, 
        make the appropriate function calls, and return the result.""",
        functions=[add_numbers, multiply_numbers],
    )

    async with math_agent:
        llm = await math_agent.attach_llm(OpenAIAugmentedLLM)
        result = await llm.generate_str(
            message=expr,
        )

        logger.info(f"Expert math result: {result}")

        return result


async def example_usage():
    async with app.run() as agent_app:
        logger = agent_app.logger
        context = agent_app.context

        outcome = await calculate(
            "Add 2 and 3, then multiply the result by 4.", context
        )
        logger.info(f"(2+3) * 4 equals {outcome}")


if __name__ == "__main__":
    start = time.time()
    asyncio.run(example_usage())
    end = time.time()
    t = end - start

    print(f"Total run time: {t:.2f}s")
