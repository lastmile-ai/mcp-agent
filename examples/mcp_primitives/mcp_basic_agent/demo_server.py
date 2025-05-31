from mcp.server.fastmcp import FastMCP
import datetime
import json

# Store server start time
SERVER_START_TIME = datetime.datetime.utcnow()

mcp = FastMCP("Resource Demo MCP Server")

# Define some static resources
STATIC_RESOURCES = {
    "demo://docs/readme": {
        "name": "README",
        "description": "A sample README file.",
        "content_type": "text/markdown",
        "content": "# Demo Resource Server\n\nThis is a sample README resource provided by the demo MCP server.",
    },
    "demo://data/users": {
        "name": "User Data",
        "description": "Sample user data in JSON format.",
        "content_type": "application/json",
        "content": json.dumps(
            [
                {"id": 1, "name": "Alice"},
                {"id": 2, "name": "Bob"},
                {"id": 3, "name": "Charlie"},
            ],
            indent=2,
        ),
    },
}


@mcp.resource("demo://docs/readme")
def get_readme():
    """Provide the README file content."""
    meta = STATIC_RESOURCES["demo://docs/readme"]
    return meta["content"]


@mcp.resource("demo://data/users")
def get_users():
    """Provide user data."""
    meta = STATIC_RESOURCES["demo://data/users"]
    return meta["content"]


@mcp.resource("demo://{city}/weather")
def get_weather(city: str) -> str:
    """Provide a simple weather report for a given city."""
    return f"It is sunny in {city} today!"


@mcp.prompt()
def echo(message: str) -> str:
    """Echo the provided message.

    This is a simple prompt that echoes back the input message.
    """
    return f"Prompt: {message}"


def main():
    """Main entry point for the MCP server."""
    mcp.run()


if __name__ == "__main__":
    main()
