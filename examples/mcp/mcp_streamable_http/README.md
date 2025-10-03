# MCP Streamable HTTP example

This example shows mcp-agent usage with a Streamable HTTP server (using the [example server](https://github.com/modelcontextprotocol/python-sdk/tree/main/examples/servers/simple-streamablehttp-stateless) in the `mcp-python` repo).

The server should connect, initialize and list its tools.

## `1` App set up

First, clone the repo and navigate to the `mcp_streamable_http` example:

```bash
git clone https://github.com/lastmile-ai/mcp-agent.git
cd mcp-agent/examples/mcp/mcp_streamable_http/
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

Start the server:

```bash
uv run stateless_server.py
```

In a new CLI terminal, run the mcp-agent application:

```bash
uv run main.py
```
