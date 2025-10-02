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

## `3` [Beta] Deploy to the cloud

### `a.` Log in to [MCP Agent Cloud](https://docs.mcp-agent.com/cloud/overview)

```bash
uv run mcp-agent login
```

### `b.` Deploy your agent with a single command

```bash
uv run mcp-agent deploy model-selector-server
```

During deployment, you can select how you would like your secrets managed.

### `c.` Connect to your deployed agent as an MCP server through any MCP client

#### Claude Desktop Integration

Configure Claude Desktop to access your agent servers by updating your `~/.claude-desktop/config.json`:

```json
"my-agent-server": {
  "command": "/path/to/npx",
  "args": [
    "mcp-remote",
    "https://[your-agent-server-id].deployments.mcp-agent.com/sse",
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

| Setting          | Value                                                          |
| ---------------- | -------------------------------------------------------------- |
| _Transport Type_ | _SSE_                                                          |
| _SSE_            | _https://[your-agent-server-id].deployments.mcp-agent.com/sse_ |
| _Header Name_    | _Authorization_                                                |
| _Bearer Token_   | _your-mcp-agent-cloud-api-token_                               |

> [!TIP]
> In the Configuration, change the request timeout to a longer time period. Since your agents are making LLM calls, it is expected that it should take longer than simple API calls.
