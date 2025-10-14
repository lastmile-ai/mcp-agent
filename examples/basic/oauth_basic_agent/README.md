# OAuth Basic MCP Agent example (client-only loopback)

This example mirrors `mcp_basic_agent` but adds GitHub MCP with OAuth using the client-only loopback flow.

## Setup

1. Register a GitHub OAuth App and add redirect URIs (at least one of):

   - `http://127.0.0.1:33418/callback`
   - `http://127.0.0.1:33419/callback`
   - `http://localhost:33418/callback`

2. Copy the secrets template and fill in your API keys / OAuth client (or export the env vars manually):

```bash
cp mcp_agent.secrets.yaml.example mcp_agent.secrets.yaml
```

3. Install deps and run:

```bash
uv pip install -r requirements.txt
# If you populated the secrets file you can skip these exports.
export GITHUB_CLIENT_ID=...
export GITHUB_CLIENT_SECRET=...
uv run main.py
```

On first run, a browser window opens to authorize GitHub; subsequent runs reuse the cached token.
