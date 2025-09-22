import asyncio
import logging
from typing import Dict, Any

from mcp.server.fastmcp import Context
import mcp.types as types
from pydantic import BaseModel, Field
from mcp_agent.app import MCPApp
from mcp_agent.server.app_server import create_mcp_server_for_app
from mcp_agent.executor.workflow import Workflow, WorkflowResult

# Initialize logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = MCPApp(name="elicitation_demo", description="Demo of workflow with elicitation")


@app.tool()
async def book_table(date: str, party_size: int, topic: str, app_ctx: Context) -> str:
    """Book a table with confirmation"""

    app.logger.info(f"Confirming table for {party_size} on {date}")

    class ConfirmBooking(BaseModel):
        confirm: bool = Field(description="Confirm booking?")
        notes: str = Field(default="", description="Special requests")

    result = await app.context.upstream_session.elicit(
        message=f"Confirm booking for {party_size} on {date}?",
        requestedSchema=ConfirmBooking.model_json_schema(),
    )

    app.logger.info(f"Result from confirmation: {result}")

    haiku = await app_ctx.upstream_session.create_message(
        messages=[
            types.SamplingMessage(
                role="user",
                content=types.TextContent(
                    type="text", text=f"Write a haiku about {topic}."
                ),
            )
        ],
        system_prompt="You are a poet.",
        max_tokens=80,
        model_preferences=types.ModelPreferences(
            hints=[types.ModelHint(name="gpt-4o-mini")],
            costPriority=0.1,
            speedPriority=0.8,
            intelligencePriority=0.1,
        ),
    )

    app.logger.info(f"Haiku: {haiku.content.text}")
    return "Done!"


@app.workflow
class TestWorkflow(Workflow[str]):
    @app.workflow_run
    async def run(self, args: Dict[str, Any]) -> WorkflowResult[str]:
        app_ctx = app.context

        date = args.get("date", "today")
        party_size = args.get("party_size", 2)
        topic = args.get("topic", "autumn")

        app.logger.info(f"Confirming table for {party_size} on {date}")

        class ConfirmBooking(BaseModel):
            confirm: bool = Field(description="Confirm booking?")
            notes: str = Field(default="", description="Special requests")

        result = await app.context.upstream_session.elicit(
            message=f"Confirm booking for {party_size} on {date}?",
            requestedSchema=ConfirmBooking.model_json_schema(),
        )

        app.logger.info(f"Result from confirmation: {result}")

        haiku = await app_ctx.upstream_session.create_message(
            messages=[
                types.SamplingMessage(
                    role="user",
                    content=types.TextContent(
                        type="text", text=f"Write a haiku about {topic}."
                    ),
                )
            ],
            system_prompt="You are a poet.",
            max_tokens=80,
            model_preferences=types.ModelPreferences(
                hints=[types.ModelHint(name="gpt-4o-mini")],
                costPriority=0.1,
                speedPriority=0.8,
                intelligencePriority=0.1,
            ),
        )

        app.logger.info(f"Haiku: {haiku.content.text}")
        return WorkflowResult(value="Done!")


async def main():
    async with app.run() as agent_app:
        # Log registered workflows and agent configurations
        logger.info(f"Creating MCP server for {agent_app.name}")

        logger.info("Registered workflows:")
        for workflow_id in agent_app.workflows:
            logger.info(f"  - {workflow_id}")
        # Create the MCP server that exposes both workflows and agent configurations
        mcp_server = create_mcp_server_for_app(agent_app)

        # Run the server
        await mcp_server.run_sse_async()


if __name__ == "__main__":
    asyncio.run(main())
