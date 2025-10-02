from mcp.server.fastmcp import FastMCP
from mcp.types import ModelPreferences, ModelHint, SamplingMessage, TextContent

mcp = FastMCP("Nested Sampling Server")


@mcp.tool()
async def get_haiku(topic: str) -> str:
    """Use MCP sampling to generate a haiku about the given topic."""
    result = await mcp.get_context().session.create_message(
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
        return result.content.text
    return "Haiku generation failed"


def main():
    mcp.run()


if __name__ == "__main__":
    main()
