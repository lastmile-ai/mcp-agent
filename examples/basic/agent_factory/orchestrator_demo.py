import asyncio

from pathlib import Path

from mcp_agent.app import MCPApp
from mcp_agent.workflows.factory import (
    load_agent_specs_from_file,
    create_llm,
    create_orchestrator,
)
from mcp.types import ModelPreferences


async def main():
    async with MCPApp(name="orchestrator_demo").run() as agent_app:
        context = agent_app.context
        context.config.mcp.servers["filesystem"].args.extend(["."])

        agents_path = Path(__file__).resolve().parent / "agents.yaml"
        specs = load_agent_specs_from_file(str(agents_path), context=context)

        # Build an LLM with a specific model id
        planner_llm = create_llm(
            agent_name="planner",
            provider="openai",
            model="gpt-4o-mini",
            context=context,
        )

        orch = create_orchestrator(
            available_agents=[planner_llm, *specs],
            provider="anthropic",
            model=ModelPreferences(
                costPriority=0.2, speedPriority=0.3, intelligencePriority=0.5
            ),
            context=context,
        )

        result = await orch.generate_str("Summarize key components in this README.md.")
        print("Orchestrator result:\n", result)


if __name__ == "__main__":
    asyncio.run(main())
