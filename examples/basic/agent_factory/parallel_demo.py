import asyncio

from mcp_agent.app import MCPApp
from mcp_agent.workflows.factory import (
    AgentSpec,
    create_llm,
    create_parallel_llm,
)


async def main():
    async with MCPApp(name="parallel_demo").run() as agent_app:
        context = agent_app.context
        context.config.mcp.servers["filesystem"].args.extend(["."])

        fan_in_llm = create_llm(
            agent_name="aggregator",
            provider="openai",
            model="gpt-4o-mini",
            context=context,
        )

        par = create_parallel_llm(
            fan_in=fan_in_llm,
            fan_out=[
                create_llm(
                    agent_name="worker1",
                    provider="openai",
                    model="gpt-4o-mini",
                    context=context,
                ),
                AgentSpec(
                    name="worker2",
                    server_names=["filesystem"],
                    instruction="Read files and summarize",
                ),
                # Functions in fan_out must return a list of messages, not a single string
                lambda _: ["fallback function path"],
            ],
            provider="openai",
            context=context,
        )

        result = await par.generate_str(
            "Summarize README and list top 3 important files."
        )
        print("Parallel result:\n", result)


if __name__ == "__main__":
    asyncio.run(main())
