# LLM Selector example

This example shows using MCP's ModelPreferences type to select a model (LLM) based on speed, cost and intelligence priorities.

https://github.com/user-attachments/assets/04257ae4-a628-4c25-ace2-6540620cbf8b

---

```plaintext
┌──────────┐      ┌─────────────────────┐
│ Selector │──┬──▶│       gpt-4o        │
└──────────┘  │   └─────────────────────┘
              │   ┌─────────────────────┐
              ├──▶│     gpt-4o-mini     │
              │   └─────────────────────┘
              │   ┌─────────────────────┐
              ├──▶│  claude-3.5-sonnet  │
              │   └─────────────────────┘
              │   ┌─────────────────────┐
              └──▶│   claude-3-haiku    │
                  └─────────────────────┘
```

## `1` App set up

First, clone the repo and navigate to the mcp_model_selector example:

```bash
git clone https://github.com/lastmile-ai/mcp-agent.git
cd mcp-agent/examples/basic/mcp_model_selector
```

Install `uv` (if you don’t have it):

```bash
pip install uv
```

Sync `mcp-agent` project dependencies:

```bash
uv sync
```

Install requirements specific to this example:

```bash
uv pip install -r requirements.txt
```

## `2a` Run locally

Run your MCP Agent app:

```bash
uv run main.py
```

### `b.` Run locally in Interactive mode

Run your MCP Agent app:

```bash
uv run interactive.py
```

## `4` [Beta] Deploy to the cloud

### `a.` Log in to [MCP Agent Cloud](https://docs.mcp-agent.com/cloud/overview)

```bash
uv run mcp-agent login
```

### `b.` Update your `mcp_agent.secrets.yaml` to mark your developer secrets (keys)

```yaml
openai:
  api_key: !developer_secret
anthropic:
  api_key: !developer_secret
# Other secrets as needed
```

### `c.` Deploy your agent with a single command
```bash
uv run mcp-agent deploy model-selector-server
```

### `d.` Connect to your deployed agent as an MCP server through any MCP client

#### Claude Desktop Integration

Configure Claude Desktop to access your agent servers by updating your `~/.claude-desktop/config.json`:

```json
"my-agent-server": {
  "command": "/path/to/npx",
  "args": [
    "mcp-remote",
    "https://[your-agent-server-id].deployments.mcp-agent-cloud.lastmileai.dev/sse",
    "--header",
    "Authorization: Bearer ${BEARER_TOKEN}"
  ],
  "env": {
        "BEARER_TOKEN": "your-mcp-agent-cloud-api-token"
      }
}
```

#### MCP Inspector

Use MCP Inspector to explore and test your agent servers:

```bash
npx @modelcontextprotocol/inspector 
```

Make sure to fill out the following settings:

| Setting | Value | 
|---|---|
| *Transport Type* | *SSE* |
| *SSE* | *https://[your-agent-server-id].deployments.mcp-agent-cloud.lastmileai.dev/sse* |
| *Header Name* | *Authorization* | 
| *Bearer Token* | *your-mcp-agent-cloud-api-token* |

> [!TIP]
> In the Configuration, change the request timeout to a longer time period. Since your agents are making LLM calls, it is expected that it should take longer than simple API calls.
