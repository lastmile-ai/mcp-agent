"""
Worker script for the Temporal workflow example.
This script starts a Temporal worker that can execute workflows and activities.
Run this script in a separate terminal window before running the main.py script.

This leverages the TemporalExecutor's start_worker method to handle the worker setup.
"""

import asyncio
import logging

from main import app
from basic import SimpleWorkflow  # noqa: F401
from evaluator_optimizer import EvaluatorOptimizerWorkflow  # noqa: F401
from orchestrator import OrchestratorWorkflow  # noqa: F401
from parallel import ParallelWorkflow  # noqa: F401
from router import RouterWorkflow  # noqa: F401
from interactive import WorkflowWithInteraction  # noqa: F401

from mcp_agent.executor.temporal import create_temporal_worker_for_app

# Initialize logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def main():
    """
    Start a Temporal worker for the example workflows using the app's executor.
    """
    async with create_temporal_worker_for_app(app) as worker:
        await worker.run()


if __name__ == "__main__":
    asyncio.run(main())
