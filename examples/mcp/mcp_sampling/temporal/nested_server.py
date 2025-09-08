from mcp.server.fastmcp import FastMCP
from mcp.types import ModelPreferences, ModelHint, SamplingMessage, TextContent
from mcp_agent.app import MCPApp
from mcp_agent.config import Settings, LoggerSettings, LogPathSettings

mcp = FastMCP("Haiku demo server")

settings = Settings(
    execution_engine="asyncio",
    logger=LoggerSettings(
        type="file",
        level="debug",
        path_settings=LogPathSettings(
            path_pattern="asyncio/logs/nested_server-{unique_id}.jsonl",
            unique_id="timestamp",
            timestamp_format="%Y%m%d_%H%M%S"),
    ),
)

app = MCPApp(
    name="haiku_agent",
    settings=settings,
)


@mcp.tool()
async def get_haiku(topic: str) -> str:
    """Use sampling to generate a haiku about the given topic."""

    app.logger.info(f"Generating haiku about topic: {topic} via sampling")
    haiku = await mcp.get_context().session.create_message(
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

    if isinstance(haiku.content, TextContent):
        app.logger.info(f"Generated haiku: {haiku.content.text}")
        return haiku.content.text
    else:
        app.logger.error(f"Haiku generation failed, unexpected content type: {haiku.content}")
        return "Haiku generation failed, unexpected content type."


def main():
    """Main entry point for the MCP server."""
    mcp.run()


if __name__ == "__main__":
    main()
