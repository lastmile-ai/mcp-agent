from mcp.server.fastmcp import FastMCP
from mcp.types import ModelPreferences, ModelHint, SamplingMessage, TextContent
from mcp_agent.app import MCPApp

mcp = FastMCP("Haiku demo server")

app = MCPApp(
    name="haiku_agent"
)

### temp: increase logging to include all details
import logging

logging.basicConfig(level=logging.DEBUG)


@mcp.tool()
async def get_haiku(topic: str) -> str:
    """Get a haiku about a given topic."""
    import os
    async with app.run() as agent_app:
        logger = agent_app.logger

        logger.info(f"Generating haiku in nested server (pid:{os.getpid()}")

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
        return haiku.content.text
    else:
        return "Haiku generation failed, unexpected content type."


def main():
    """Main entry point for the MCP server."""
    mcp.run()


if __name__ == "__main__":
    main()
