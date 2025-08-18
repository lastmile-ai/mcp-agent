# Langfuse Trace Exporter Example

This example shows how to configure a Langfuse OTLP trace exporter for use in `mcp-agent` by configuring the
`otel.otlp_settings` with the expected endpoint and headers.
Following information from https://langfuse.com/integrations/native/opentelemetry

## `1` App set up

First, clone the repo and navigate to the tracing/langfuse example:

```bash
git clone https://github.com/lastmile-ai/mcp-agent.git
cd mcp-agent/examples/tracing/langfuse
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

Obtain a secret and public API key for your desired Langfuse project and then generate a base-64 encoded AUTH_STRING in a terminal:

```bash
echo -n "pk-your-public-key:sk-your-secret-key" | base64
```

In `mcp_agent.secrets.yaml` set the Authorization header for OTLP:

```yaml
otel:
  otlp_settings:
    headers:
      Authorization: "Basic AUTH_STRING"
```

Lastly, ensure the proper trace endpoint is configured for the `otel.otlp_settings.endpoint` in `mcp_agent.yaml` for the relevant
Langfuse data region.

## `4` Run locally

In a terminal, run:

```bash
uv run main.py
```

<img width="2160" alt="Image" src="https://github.com/user-attachments/assets/664da099-ec50-4fa8-bb89-9e6fa9880d95" />
