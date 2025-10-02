# MCP Agent Intent Classification Workflow example

This example shows using intent classification workflow, which is a close sibling of the [router workflow](../workflow_router/). The example uses both the OpenAI embedding intent classifier and the OpenAI LLM intent classifier.

## `1` App set up

First, clone the repo and navigate to the workflow intent classifier example:

```bash
git clone https://github.com/lastmile-ai/mcp-agent.git
cd mcp-agent/examples/workflows/workflow_intent_classifier
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

## `2` Set up environment variables

Copy and configure your secrets and env variables:

```bash
cp mcp_agent.secrets.yaml.example mcp_agent.secrets.yaml
```

Then open `mcp_agent.secrets.yaml` and add your OpenAI api key.

## (Optional) Configure tracing

In `mcp_agent.config.yaml`, you can set `otel` to `enabled` to enable OpenTelemetry tracing for the workflow.
You can [run Jaeger locally](https://www.jaegertracing.io/docs/2.5/getting-started/) to view the traces in the Jaeger UI.

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
uv run mcp-agent deploy workflow-intent-classifier
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
