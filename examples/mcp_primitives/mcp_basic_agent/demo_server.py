from fastmcp import FastMCP, Context
from mcp.types import ModelPreferences, ModelHint
import json

mcp = FastMCP("Resource Demo MCP Server")


@mcp.resource("demo://data/friends")
def get_users():
    """Provide my friend list."""
    return (
        json.dumps(
            [
                {"id": 1, "friend": "Alice"},
            ],
        ),
    )


@mcp.prompt()
def get_haiku_prompt(topic: str) -> str:
    """Get a haiku prompt about a given topic."""
    return f"I am fascinated about {topic}. Can you generate a haiku combining {topic} + my friend name?"


@mcp.tool()
async def get_haiku(topic: str, ctx: Context) -> str:
    """Get a haiku about a given topic."""
    haiku = await ctx.sample(
        messages=f"Generate a haiku about {topic}.",
        system_prompt="You are a poet.",
        max_tokens=100,
        model_preferences=ModelPreferences(
            hints=[ModelHint(name="gpt-4o-mini")],
            costPriority=0.1,
            speedPriority=0.8,
            intelligencePriority=0.1,
        ),
        temperature=0.7,
    )
    return haiku.text


def main():
    """Main entry point for the MCP server."""
    mcp.run()


if __name__ == "__main__":
    main()
