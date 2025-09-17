# Sampling Server

Minimal server demonstrating LLM sampling.

## Run

```bash
uv run server.py
```

Connect with the minimal client:

```bash
uv run client.py
```

Tools:

- `sample_haiku(topic: str)` — generates a short poem using configured LLM settings.

Add your API key(s) to `mcp_agent.secrets.yaml` or environment variables (e.g. `OPENAI_API_KEY`).

## Deploy to Cloud (optional)

1) Set API keys in `mcp_agent.secrets.yaml`.

2) Deploy from this directory:

```bash
uv run mcp-agent deploy sampling --config-dir .
```

Use the returned URL with `/sse` in an MCP client and include the bearer token if needed.
