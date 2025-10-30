# Observability Example (OpenTelemetry + Langfuse)

This example demonstrates how to instrument an mcp-agent application with observability features using OpenTelemetry and an OTLP exporter (Langfuse). It shows how to automatically trace tool calls, workflows, LLM calls, and add custom tracing spans.

## What's included

- `main.py` – exposes a `grade_story_async` tool that uses parallel LLM processing with multiple specialized agents (proofreader, fact checker, style enforcer, and grader). Demonstrates both automatic instrumentation by mcp-agent and manual OpenTelemetry span creation.
- `mcp_agent.config.yaml` – configures the execution engine, logging, and enables OpenTelemetry with a custom service name.
- `mcp_agent.secrets.yaml.example` – template for configuring API keys and the Langfuse OTLP exporter endpoint with authentication headers.
- `requirements.txt` – lists dependencies including mcp-agent and OpenAI.

## Features

- **Automatic instrumentation**: Tool calls, workflows, and LLM interactions are automatically traced by mcp-agent
- **Custom tracing**: Example of adding manual OpenTelemetry spans with custom attributes
- **Langfuse integration**: OTLP exporter configuration for sending traces to Langfuse; you can alternatively use your preferred OTLP exporter endpoint

## Prerequisites

- Python 3.10+
- [UV](https://github.com/astral-sh/uv) package manager
- API key for OpenAI
- Langfuse account (for observability dashboards)

## Configuration

Before running the example, you'll need to configure API keys and observability settings.

### API Keys and Observability Setup

1. Copy the example secrets file:

```bash
cd examples/cloud/observability
cp mcp_agent.secrets.yaml.example mcp_agent.secrets.yaml
```

2. Edit `mcp_agent.secrets.yaml` to add your credentials:

```yaml
openai:
  api_key: "your-openai-api-key"

otel:
  exporters:
    - otlp:
        endpoint: "https://us.cloud.langfuse.com/api/public/otel/v1/traces"
        headers:
          Authorization: "Basic AUTH_STRING"
```

3. Generate the Langfuse basic auth token:

   a. Sign up for a [Langfuse account](https://langfuse.com/) if you don't have one

   b. Obtain your Langfuse public and secret keys from the project settings

   c. Generate the base64-encoded basic auth token:

   ```bash
   echo -n "pk-lf-YOUR-PUBLIC-KEY:sk-lf-YOUR-SECRET-KEY" | base64
   ```

   d. Replace `AUTH_STRING` in the config with the generated base64 string

   > See [Langfuse OpenTelemetry documentation](https://langfuse.com/integrations/native/opentelemetry#opentelemetry-endpoint) for more details, including the OTLP endpoint for EU data region.

## Test Locally

1. Install dependencies:

```bash
uv pip install -r requirements.txt
```

2. Start the mcp-agent server locally with SSE transport:

```bash
uv run main.py
```

3. Use [MCP Inspector](https://github.com/modelcontextprotocol/inspector) to explore and test the server:

```bash
npx @modelcontextprotocol/inspector --transport sse --server-url http://127.0.0.1:8000/sse
```

4. In MCP Inspector, test the `grade_story_async` tool with a sample story. The tool will:

   - Create a custom trace span for the magic number calculation
   - Automatically trace the parallel LLM execution
   - Send all traces to Langfuse for visualization

5. View your traces in the Langfuse dashboard to see:
   - Complete execution flow
   - Timing for each agent
   - LLM calls and responses
   - Custom span attributes

## Deploy to mcp-agent Cloud

You can deploy this MCP-Agent app as a hosted mcp-agent app in the Cloud.

1. In your terminal, authenticate into mcp-agent cloud by running:

```bash
uv run mcp-agent login
```

2. You will be redirected to the login page, create an mcp-agent cloud account through Google or Github

3. Set up your mcp-agent cloud API Key and copy & paste it into your terminal

```bash
uv run mcp-agent login
INFO: Directing to MCP Agent Cloud API login...
Please enter your API key 🔑:
```

4. In your terminal, deploy the MCP app:

```bash
uv run mcp-agent deploy observability-example
```

5. When prompted, specify the type of secret to save your API keys. Select (1) deployment secret so that they are available to the deployed server.

The `deploy` command will bundle the app files and deploy them, producing a server URL of the form:
`https://<server_id>.deployments.mcp-agent.com`.

## MCP Clients

Since the mcp-agent app is exposed as an MCP server, it can be used in any MCP client just
like any other MCP server.

### MCP Inspector

You can inspect and test the deployed server using [MCP Inspector](https://github.com/modelcontextprotocol/inspector):

```bash
npx @modelcontextprotocol/inspector --transport sse --server-url https://<server_id>.deployments.mcp-agent.com/sse
```

This will launch the MCP Inspector UI where you can:

- See all available tools
- Test the `grade_story_async` and `ResearchWorkflow` workflow execution

Make sure Inspector is configured with the following settings:

| Setting          | Value                                               |
| ---------------- | --------------------------------------------------- |
| _Transport Type_ | _SSE_                                               |
| _SSE_            | _https://[server_id].deployments.mcp-agent.com/sse_ |
| _Header Name_    | _Authorization_                                     |
| _Bearer Token_   | _your-mcp-agent-cloud-api-token_                    |

> [!TIP]
> In the Configuration, change the request timeout to a longer time period. Since your agents are making LLM calls, it is expected that it should take longer than simple API calls.
