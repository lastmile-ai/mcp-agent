# Simplest Usage of MCP Agent - Hello World!

This MCP Agent app uses a client to connect to the [fetch server](https://github.com/modelcontextprotocol/servers/tree/main/src/fetch) and the [filesystem server](https://github.com/modelcontextprotocol/servers/tree/main/src/filesystem) to print the tools available for each MCP server.

```plaintext
┌──────────┐      ┌──────────────┐
│  Client  │──┬──▶│  Fetch       │
└──────────┘  │   │  MCP Server  │
              │   └──────────────┘
              │   ┌──────────────┐
              └──▶│  Filesystem  │
                  │  MCP Server  │
                  └──────────────┘
```

## `1` App set up

First, clone the repo and navigate to the hello world example:

```bash
git clone https://github.com/lastmile-ai/mcp-agent.git
cd mcp-agent/examples/basic/mcp_hello_world
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

Then open `mcp_agent.secrets.yaml` and add your api key for your preferred LLM and keys/tokens for your MCP servers.

## `3` Run locally

Run your MCP Agent app:

```bash
uv run main.py
```
