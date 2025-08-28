from mcp.server.fastmcp import FastMCP
from mcp.types import ModelPreferences, ModelHint, SamplingMessage, TextContent
import json

mcp = FastMCP("Resource Demo MCP Server")


@mcp.resource("demo://docs/readme")
def get_readme():
    """Provide the README file content."""
    return "# Demo Resource Server\n\nThis is a sample README resource provided by the demo MCP server."


@mcp.prompt()
def echo(message: str) -> str:
    """Echo the provided message.

    This is a simple prompt that echoes back the input message.
    """
    return f"Prompt: {message}"


@mcp.resource("demo://data/friends")
def get_users():
    """Provide my friend list."""
    return (
        json.dumps(
            [
                {"id": 1, "friend": "Alice"},
            ]
        )
    )


@mcp.prompt()
def get_haiku_prompt(topic: str) -> str:
    """Get a haiku prompt about a given topic."""
    return f"I am fascinated about {topic}. Can you generate a haiku combining {topic} + my friend name?"


@mcp.tool()
async def get_haiku(topic: str) -> str:
    """Get a haiku about a given topic."""
    haiku = await mcp.get_context().session.create_message(
        messages=[
            SamplingMessage(
                role="user",
                content=TextContent(
                    type="text", text=f"Generate a haiku about {topic}."
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
