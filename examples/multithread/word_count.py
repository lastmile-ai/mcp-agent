from mcp.server.fastmcp import FastMCP


mcp = FastMCP("Script Duration Server")


@mcp.tool()
def get_script_word_count(script: str) -> int:
    """Return the number of whitespace-separated tokens in *script*."""
    return len(script.split())


if __name__ == "__main__":
    mcp.run()
