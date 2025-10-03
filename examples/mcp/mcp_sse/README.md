# SSE example

This example shows how to use an SSE server with mcp-agent.

- `server.py` is a simple server that runs on localhost:8000
- `main.py` is the mcp-agent client that uses the SSE server.py

<img width="1848" alt="image" src="https://github.com/user-attachments/assets/94c1e17c-a8d7-4455-8008-8f02bc404c28" />

## `1` App set up

First, clone the repo and navigate to the mcp_sse example:

```bash
git clone https://github.com/lastmile-ai/mcp-agent.git
cd mcp-agent/examples/mcp/mcp_sse
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

In one terminal, run:

```bash
uv run server.py
```

In another terminal, run:

```bash
uv run main.py
```
