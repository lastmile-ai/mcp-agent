# Basic MCP Agent example

This MCP Agent app shows a "finder" Agent which has access to the [fetch](https://github.com/modelcontextprotocol/servers/tree/main/src/fetch) and [filesystem](https://github.com/modelcontextprotocol/servers/tree/main/src/filesystem) MCP servers.

You can ask it information about local files or URLs, and it will make the determination on what to use at what time to satisfy the request.

## <img width="2160" alt="Image" src="https://github.com/user-attachments/assets/14cbfdf4-306f-486b-9ec1-6576acf0aeb7" />

```plaintext
┌──────────┐      ┌──────────────┐
│  Finder  │──┬──▶│  Fetch       │
│  Agent   │  │   │  MCP Server  │
└──────────┘  │   └──────────────┘
              |   ┌──────────────┐
              └──▶│  Filesystem  │
                  │  MCP Server  │
                  └──────────────┘
```

## `1` App set up

First, clone the repo and navigate to the basic‑agent example:

```bash
git clone https://github.com/lastmile-ai/mcp-agent.git
cd mcp-agent/examples/basic/mcp_basic_agent
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

## `2` Set up API keys

You have three options to provide secrets:

- mcp_agent.secrets.yaml (existing pattern)
- .env file (now supported)
- MCP_APP_SETTINGS_PRELOAD (secure preload; recommended for production)

Recommended for local dev (choose one):

1. .env file

```bash
cp .env.example .env
# Edit .env and set OPENAI_API_KEY / ANTHROPIC_API_KEY, etc.
```

2. Secrets YAML

```bash
cp mcp_agent.secrets.yaml.example mcp_agent.secrets.yaml
# Edit mcp_agent.secrets.yaml and set your API keys
```

3. Preload (process-scoped)

```bash
export MCP_APP_SETTINGS_PRELOAD="$(python - <<'PY'
from pydantic_yaml import to_yaml_str
from mcp_agent.config import Settings, OpenAISettings
print(to_yaml_str(Settings(openai=OpenAISettings(api_key='sk-...'))))
PY
)"
uv run main.py
```

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
uv run mcp-agent deploy my-first-agent
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
