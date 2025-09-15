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

