# Xquik MCP Agent Example

This example connects `mcp-agent` to the hosted Xquik MCP server over Streamable HTTP.
Use it when an agent needs X/Twitter context such as public post search, user lookup,
trends, or approval-gated actions through Xquik.

The agent first lists the remote Xquik tools, then asks the LLM to identify a
read-only endpoint for an X research task. Keep write actions behind an explicit
human approval step in your own workflow.

## `1` App set up

Clone the repo and navigate to the example:

```bash
git clone https://github.com/lastmile-ai/mcp-agent.git
cd mcp-agent/examples/mcp/mcp_xquik/
```

Install `uv` if needed:

```bash
pip install uv
```

Sync the project dependencies:

```bash
uv sync
```

Install the example requirements:

```bash
uv pip install -r requirements.txt
```

## `2` Configure keys

Copy the example files:

```bash
cp .env.example .env
cp mcp_agent.secrets.yaml.example mcp_agent.secrets.yaml
```

Set `XQUIK_API_KEY` in `.env`, then add your OpenAI API key in
`mcp_agent.secrets.yaml`.

Get a Xquik API key from <https://dashboard.xquik.com/en/account>.

Xquik is a hosted, closed-source service. It is independent of X Corp.

## `3` Run locally

```bash
uv run main.py
```

The example uses the Xquik MCP remote at <https://xquik.com/mcp> and passes the
API key in the `x-api-key` header.
