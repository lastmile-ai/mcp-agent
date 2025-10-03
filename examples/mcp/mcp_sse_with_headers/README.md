# MCP Agent example

This example shows a basic agent that can connect to an MCP server over SSE with auth headers.

<img width="2160" alt="Image" src="https://github.com/user-attachments/assets/14cbfdf4-306f-486b-9ec1-6576acf0aeb7" />

## `1` App set up

First, clone the repo and navigate to the mcp_sse_with_headers example:

```bash
git clone https://github.com/lastmile-ai/mcp-agent.git
cd mcp-agent/examples/mcp/mcp_sse_with_headers
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

## `2` Update with your hosted SSE MCP server

Open `mcp_agent.config.yaml` file and update the file with the correct links to a hosted SSE
server and your HTTP headers.

## `2.1` Set up secrets and environment variables

Copy and configure your secrets and env variables:

```bash
cp mcp_agent.secrets.yaml.example mcp_agent.secrets.yaml
```

Then open `mcp_agent.secrets.yaml` and add your api key for your preferred LLM and keys/tokens for your MCP servers.

## `3` Run locally

Run your MCP Agent app:

```bash
uv run main.py
```
