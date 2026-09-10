"""Expose the deterministic validator through a local stdio MCP server."""

from mcp.server.fastmcp import FastMCP
from validator import validate_csv

server = FastMCP("csv-preflight", log_level="WARNING")
server.tool()(validate_csv)

if __name__ == "__main__":
    server.run(transport="stdio")
