# OAuth Basic MCP Agent example (client-only loopback)

This example mirrors `mcp_basic_agent` but adds GitHub MCP with OAuth using the client-only loopback flow.

## Setup

1. Register a GitHub OAuth App and add redirect URIs (at least one of):

   - `http://127.0.0.1:33418/callback`
   - `http://127.0.0.1:33419/callback`
   - `http://localhost:33418/callback`

2. Install deps and run:

```bash
uv sync
uv pip install -r requirements.txt
export GITHUB_CLIENT_ID=...
export GITHUB_CLIENT_SECRET=...
uv run main.py
```

On first run, a browser window opens to authorize GitHub; subsequent runs reuse the cached token.
