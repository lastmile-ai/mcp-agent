import asyncio
from dataclasses import dataclass
from typing import List

from mcp_agent.app import MCPApp
from mcp_agent.agents.agent import Agent
from mcp_agent.executor.workflow import Workflow, WorkflowResult
from mcp_agent.workflows.llm.augmented_llm_openai import OpenAIAugmentedLLM

app = MCPApp(name="temporal_planner_example")


@dataclass
class PlanStep:
    description: str
    tool_to_use: str = "slow_shell_command"


def slow_shell_command(command: str) -> str:
    """Simulate a long running shell command."""
    import time

    time.sleep(2)
    return f"[slow-shell] {command.strip()}"


planner_agent = Agent(
    name="planner",
    server_names=["filesystem"],
)
planner_llm = OpenAIAugmentedLLM(agent=planner_agent)

research_agent = Agent(
    name="researcher",
    server_names=["filesystem"],
    functions=[slow_shell_command],
)
research_llm = OpenAIAugmentedLLM(agent=research_agent)


@app.workflow
class PlannerSubagentWorkflow(Workflow[str]):
    """Workflow that delegates plan steps to sub-agents/tool calls."""

    @app.workflow_run
    async def run(self, task: str) -> WorkflowResult[str]:
        plan = await self.generate_plan(task)
        step_outputs = []
        for step in plan:
            result = await self.execute_step(step)
            step_outputs.append(f"{step.description}: {result}")
        summary = await self.summarize_results(task, step_outputs)
        return WorkflowResult(value=summary)

    async def generate_plan(self, task: str) -> List[PlanStep]:
        plan_prompt = (
            "You are an expert planner. Break the objective into 2 concrete steps. "
            "Return one step per line in the format 'Step: <action>'.\n"
            f"Objective: {task}"
        )
        plan_text = await planner_llm.generate_str(plan_prompt)
        steps: List[PlanStep] = []
        for line in plan_text.splitlines():
            line = line.strip("-* ")
            if not line:
                continue
            if ":" in line:
                _, action = line.split(":", 1)
                action = action.strip()
            else:
                action = line
            if action:
                steps.append(PlanStep(description=action))
            if len(steps) >= 2:
                break
        if not steps:
            steps = [
                PlanStep(description=f"Collect background on {task}"),
                PlanStep(description=f"Summarize findings for {task}"),
            ]
        return steps

    async def execute_step(self, step: PlanStep) -> str:
        tool_result = await research_llm.agent.call_tool(
            step.tool_to_use,
            {"command": step.description},
        )
        text_blocks = [
            block.text for block in tool_result.content if block.type == "text"
        ]
        return text_blocks[0] if text_blocks else ""

    async def summarize_results(self, task: str, results: List[str]) -> str:
        summary_prompt = (
            f"Summarize these notes for '{task}' in 3 sentences:\n"
            + "\n".join(f"- {line}" for line in results)
        )
        return await research_llm.generate_str(summary_prompt)


async def main():
    async with app.run() as running_app:
        executor = running_app.executor
        handle = await executor.start_workflow(
            "PlannerSubagentWorkflow",
            task="research the benefits of test-driven development",
            workflow_id="planner-subagent-sample",
        )
        result = await handle.result()
        print("Final summary:\n", result.value)


if __name__ == "__main__":
    asyncio.run(main())
