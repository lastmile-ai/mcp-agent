from pydantic import BaseModel
from mcp.server.fastmcp import FastMCP
from mcp.server.elicitation import elicit_with_validation, AcceptedElicitation

mcp = FastMCP("Nested Elicitation Server")


class Confirmation(BaseModel):
    confirm: bool


@mcp.tool()
async def confirm_action(action: str) -> str:
    """Ask the user to confirm an action via elicitation."""
    ctx = mcp.get_context()
    res = await elicit_with_validation(
        ctx.session,
        message=f"Do you want to {action}?",
        schema=Confirmation,
    )
    if isinstance(res, AcceptedElicitation) and res.data.confirm:
        return f"Action '{action}' confirmed by user"
    return f"Action '{action}' declined by user"


def main():
    mcp.run()


if __name__ == "__main__":
    main()
