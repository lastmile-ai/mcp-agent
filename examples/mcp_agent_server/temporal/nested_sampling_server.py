from mcp.server.fastmcp import Context, FastMCP
from mcp.types import ModelHint, ModelPreferences, SamplingMessage, TextContent

mcp = FastMCP("Nested Sampling Server")


@mcp.tool()
async def get_haiku(topic: str, ctx: Context | None = None) -> str:
    """Use MCP sampling to generate a haiku about the given topic."""
    context = ctx or mcp.get_context()
    await context.info(f"[temporal_nested_sampling] topic='{topic}'")
    result = await context.session.create_message(
        messages=[
            SamplingMessage(
                role="user",
                content=TextContent(
                    type="text", text=f"Generate a quirky haiku about {topic}."
                ),
            )
        ],
        system_prompt="You are a poet.",
        max_tokens=100,
        temperature=0.7,
        model_preferences=ModelPreferences(
            hints=[ModelHint(name="gpt-4o-mini")],
            costPriority=0.1,
            speedPriority=0.8,
            intelligencePriority=0.1,
        ),
    )

    if isinstance(result.content, TextContent):
        await context.info("[temporal_nested_sampling] returning haiku")
        return result.content.text
    return "Haiku generation failed"


def main():
    mcp.run()


if __name__ == "__main__":
    main()
