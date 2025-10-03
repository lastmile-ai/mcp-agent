# MCP Functions Agent Example

This example shows a "math" Agent using manually-defined functions to compute simple math results for a user request.

The agent will determine, based on the request, which functions to call and in what order.

<img width="2160" alt="Image" src="https://github.com/user-attachments/assets/14cbfdf4-306f-486b-9ec1-6576acf0aeb7" />

---

```plaintext
┌──────────┐      ┌───────────────────┐
│   Math   │──┬──▶│   add function    │
│   Agent  │  │   └───────────────────┘
└──────────┘  │   ┌───────────────────┐
              └──▶│ multiply function │
                  └───────────────────┘
```

## `1` App set up

First, clone the repo and navigate to the functions example:

```bash
git clone https://github.com/lastmile-ai/mcp-agent.git
cd mcp-agent/examples/basic/functions
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

## `2` Set up secrets and environment variables

Copy and configure your secrets and env variables:

```bash
cp mcp_agent.secrets.yaml.example mcp_agent.secrets.yaml
```

Then open `mcp_agent.secrets.yaml` and add your api key for your preferred LLM for your MCP servers.

## `3` Run locally

Run your MCP Agent app:

```bash
uv run main.py
```

## `4` [Beta] Deploy to the cloud

### `a.` Log in to [MCP Agent Cloud](https://docs.mcp-agent.com/cloud/overview)

```bash
uv run mcp-agent login
```

### `b.` Deploy your agent with a single command
```bash
uv run mcp-agent deploy mcp-function-service
```

### `c.` Connect to your deployed agent as an MCP server through any MCP client

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
