import logging

from mcp.server.fastmcp import Context
from pydantic import BaseModel, Field
from mcp_agent.app import MCPApp

# Initialize logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = MCPApp(name="elicitation_demo", description="Demo of workflow with elicitation")


# mcp_context for fastmcp context
@app.tool()
async def book_table(date: str, party_size: int, app_ctx: Context) -> str:
    """Book a table with confirmation"""

    # Schema must only contain primitive types (str, int, float, bool)
    class ConfirmBooking(BaseModel):
        confirm: bool = Field(description="Confirm booking?")
        notes: str = Field(default="", description="Special requests")

    app.logger.info(
        f"Confirming the use wants to book a table for {party_size} on {date} via elicitation"
    )

    result = await app.context.upstream_session.elicit(
        message=f"Confirm booking for {party_size} on {date}?",
        requestedSchema=ConfirmBooking.model_json_schema(),
    )

    app.logger.info(f"Result from confirmation: {result}")

    if result.action == "accept":
        data = ConfirmBooking.model_validate(result.content)
        if data.confirm:
            return f"Booked! Notes: {data.notes or 'None'}"
        return "Booking cancelled"
    elif result.action == "decline":
        return "Booking declined"
    elif result.action == "cancel":
        return "Booking cancelled"
