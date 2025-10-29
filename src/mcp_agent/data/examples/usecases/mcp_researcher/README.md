# MCP Researcher example

This example shows a research assistant agent which has access to internet search (via ['brave'](https://github.com/modelcontextprotocol/servers/tree/main/src/brave-search)), website [fetch](https://github.com/modelcontextprotocol/servers/tree/main/src/fetch), a python interpreter, and the [filesystem](https://github.com/modelcontextprotocol/servers/tree/main/src/filesystem).

The research assistant agent can produce an investment report by utilizing search, python code, website fetch, and write the report to your filesystem.

```plaintext
┌──────────┐      ┌──────────────┐
│ Research │──┬──▶│  Fetch       │
│  Agent   │  │   │  MCP Server  │
└──────────┘  │   └──────────────┘
              │   ┌──────────────┐
              ├──▶│  Filesystem  │
              │   │  MCP Server  │
              │   └──────────────┘
              │   ┌──────────────┐
              ├──▶│  Brave       │
              │   │  MCP Server  │
              │   └──────────────┘
              │   ┌──────────────┐
              └──▶│  Python      │
                  │  Interpreter │
                  └──────────────┘
```

## `1` App set up

First, clone the repo and navigate to the slack agent example:

```bash
git clone https://github.com/lastmile-ai/mcp-agent.git
cd mcp-agent/examples/usecases/mcp_researcher
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

Then open `mcp_agent.secrets.yaml` and add your api key for your preferred LLM and your API key for the [Brave API](https://brave.com/search/api/).

## `3` Run locally

Run your MCP Agent app:

```bash
uv run main.py
```
