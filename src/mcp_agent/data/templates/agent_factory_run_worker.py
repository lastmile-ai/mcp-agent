"""
Temporal worker script for the factory demo.
Run this in a separate terminal when using the Temporal execution engine.
"""

import asyncio
import logging

from mcp_agent.executor.temporal import create_temporal_worker_for_app

from main import app


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def main():
    logger.info("Starting Temporal worker for factory demo")
    async with create_temporal_worker_for_app(app) as worker:
        await worker.run()


if __name__ == "__main__":
    asyncio.run(main())
