# SSE example

This example shows distributed tracing between a client and an SSE server. `mcp-agent` automatically propagates
trace context in the client requests to the server; the server should be instrumented with opentelemetry and
have MCPInstrumentor auto-instrumentation configured (from `openinference-instrumentation-mcp`).

- `server.py` is a simple server that runs on localhost:8000
- `main.py` is the mcp-agent client that uses the SSE server.py

<img width="1848" alt="image" src="https://github.com/user-attachments/assets/94c1e17c-a8d7-4455-8008-8f02bc404c28" />

## `1` App set up

First, clone the repo and navigate to the tracing/mcp example:

```bash
git clone https://github.com/lastmile-ai/mcp-agent.git
cd mcp-agent/examples/tracing/mcp
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

## `3` Configure Jaeger Collector

[Run Jaeger locally](https://www.jaegertracing.io/docs/2.5/getting-started/) and then update the `mcp_agent.config.yaml` for this example to have `otel.otlp_settings.endpoint` point to the collector endpoint (e.g. `http://localhost:4318/v1/traces` is the default for Jaeger via HTTP).

## `4` Run locally

In one terminal, run:

```bash
uv run server.py
```

In another terminal, run:

```bash
uv run main.py
```

<img width="2160" alt="Image" src="https://github.com/user-attachments/assets/06db5a26-ab07-4454-8e87-295bde7ff6ae" />
