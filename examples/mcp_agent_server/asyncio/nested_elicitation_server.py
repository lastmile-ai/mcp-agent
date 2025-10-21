from pydantic import BaseModel
from mcp.server.fastmcp import Context, FastMCP
from mcp.server.elicitation import elicit_with_validation, AcceptedElicitation

mcp = FastMCP("Nested Elicitation Server")


class Confirmation(BaseModel):
    confirm: bool


@mcp.tool()
async def confirm_action(action: str, ctx: Context | None = None) -> str:
    """Ask the user to confirm an action via elicitation."""
    context = ctx or mcp.get_context()
    await context.info(f"[nested_elicitation] requesting '{action}' confirmation")
    res = await elicit_with_validation(
        context.session,
        message=f"Do you want to {action}?",
        schema=Confirmation,
    )
    if isinstance(res, AcceptedElicitation) and res.data.confirm:
        if ctx:
            await context.info(f"[nested_elicitation] '{action}' accepted")
        return f"Action '{action}' confirmed by user"
    if ctx:
        await context.warning(f"[nested_elicitation] '{action}' declined")
    return f"Action '{action}' declined by user"


def main():
    mcp.run()


if __name__ == "__main__":
    main()
