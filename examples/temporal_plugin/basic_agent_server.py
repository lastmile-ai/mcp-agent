import logging
import asyncio
from main import app
from mcp_agent.server.app_server import create_mcp_server_for_app
from basic_workflow import BasicWorkflow

# Initialize logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app.register_temporal_workflows([BasicWorkflow])


async def main():
    async with app.run() as agent_app:
        logger.info(f"Creating MCP server for {agent_app.name}")

        logger.info("Registered workflows:")
        for workflow_id in agent_app.workflows:
            logger.info(f"  - {workflow_id}")

        mcp_server = create_mcp_server_for_app(agent_app)

        await mcp_server.run_sse_async()


if __name__ == "__main__":
    asyncio.run(main())
