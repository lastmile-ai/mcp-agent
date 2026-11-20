"""Example: make a workflow's successful result conditional on GRF acceptance."""

import asyncio
from pathlib import Path

from mcp_agent.app import MCPApp
from mcp_agent.executor.workflow import Workflow, WorkflowResult

from grf_gate import complete_grf_task

app = MCPApp(name="grf_gated_workflow")
PROJECT = Path(__file__).resolve().parent / ".grf-project"


@app.workflow
class DraftWorkflow(Workflow[str]):
    async def run(self) -> WorkflowResult[str]:
        deliverable = "deliverable.txt"
        output = PROJECT / deliverable
        output.write_text("Example workflow output\n", encoding="utf-8")

        # GRF reruns the project's declared checks and hashes this evidence
        # before it records task completion. On failure, the exception makes
        # mcp-agent's workflow status "error" rather than "completed".
        await asyncio.to_thread(
            complete_grf_task,
            PROJECT,
            "Created and checked the example workflow deliverable",
            [deliverable],
        )
        return WorkflowResult(value=str(output))


async def main() -> None:
    async with app.run() as running_app:
        workflow = await DraftWorkflow.create(context=running_app.context)
        execution = await workflow.run_async()
        print(f"Started workflow {execution.workflow_id} ({execution.run_id})")
        while True:
            status = await workflow.get_status()
            if not status["running"]:
                break
            await asyncio.sleep(0.1)
        if not status.get("completed"):
            raise RuntimeError(status.get("error") or "Workflow did not complete")
        print(status["result"])


if __name__ == "__main__":
    asyncio.run(main())
