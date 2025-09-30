"""
Temporal safe deployment example with workflow replay verification.

This example demonstrates the recommended pattern for safe Temporal deployments by
implementing a two-phase deployment strategy:

Phase 1 - Verification:
  Run replay tests against recent workflow histories to ensure code changes maintain
  determinism. This catches breaking changes before they affect production.

Phase 2 - Deployment:
  Deploy the verified worker code to handle new workflow executions.

Usage:
  uv run replay.py verify  # Test workflow determinism before deployment
  uv run replay.py run     # Run the worker in production

This pattern ensures that workflow code changes don't break existing executions,
which is critical for Temporal's durability guarantees. By separating verification
from production deployment, you can safely iterate on workflow logic.
"""

import asyncio
import argparse
from datetime import datetime, timedelta, timezone
from temporalio.client import Client
from temporalio.worker import Replayer, Worker
from basic_workflow import BasicWorkflow
from orchestrator import OrchestratorWorkflow
from parallel_agent import ParallelAgentWorkflow
from router import RouterWorkflow
from evaluator_optimizer import EvaluatorOptimizerWorkflow
from mcp_agent.executor.temporal.plugin import MCPAgentPlugin
from mcp_agent.app import MCPApp


async def main():
    parser = argparse.ArgumentParser(prog="MyTemporalWorker")
    parser.add_argument("mode", choices=["verify", "run"])
    args = parser.parse_args()

    temporal_url = "localhost:7233"
    task_queue = "mcp-agent"
    my_workflows = [
        BasicWorkflow,
        OrchestratorWorkflow,
        ParallelAgentWorkflow,
        RouterWorkflow,
        EvaluatorOptimizerWorkflow,
    ]
    my_activities = []

    app = MCPApp(name="mcp_basic_agent")
    async with app.run() as running_app:
        plugin = MCPAgentPlugin(running_app)

        client = await Client.connect(
            temporal_url,
            plugins=[plugin],
        )

        if args.mode == "verify":
            start_time = (datetime.now(timezone.utc) - timedelta(hours=10)).isoformat()
            workflows = client.list_workflows(
                f"TaskQueue='{task_queue}' AND StartTime > '{start_time}' AND ExecutionStatus='Completed'",
                limit=100,
            )
            histories = workflows.map_histories()
            replayer = Replayer(workflows=my_workflows, plugins=[plugin])
            results = await replayer.replay_workflows(histories)
            return results
        else:
            worker = Worker(
                client,
                task_queue=task_queue,
                workflows=my_workflows,
                activities=my_activities,
            )
            await worker.run()


if __name__ == "__main__":
    asyncio.run(main())
