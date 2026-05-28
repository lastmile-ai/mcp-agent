# Bocha Search MCP Agent

This example connects `mcp-agent` to the Bocha Search MCP server over stdio and
calls the `bocha_web_search` tool.

## Setup

Clone the Bocha MCP server separately:

```bash
git clone https://github.com/BochaAI/bocha-search-mcp.git /path/to/bocha-search-mcp
```

Set the runtime secrets and local server path:

```bash
export BOCHA_API_KEY="sk-..."
export BOCHA_SEARCH_MCP_DIR="/path/to/bocha-search-mcp"
```

On Windows CMD:

```cmd
set "BOCHA_API_KEY=sk-..."
set "BOCHA_SEARCH_MCP_DIR=D:\path\to\bocha-search-mcp"
```

Run the example:

```bash
cd /path/to/mcp-agent/examples/usecases/bocha_search_mcp_agent
uv run --project /path/to/mcp-agent python main.py
```

The script lists the Bocha MCP tools and performs a small web search through
`bocha_web_search`. API keys are read from the current process environment and
are not stored in `mcp_agent.config.yaml`.
