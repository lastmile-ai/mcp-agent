# Reference Agent Server

This is a clean, strongly-typed example of an MCP Agent server showcasing:

- Agent behavior with MCP servers (fetch + filesystem) and an LLM
- Tools implemented with `@app.tool` and `@app.async_tool`
- Notifications and logging via `app.logger`
- Elicitation (user confirmation) proxied to the upstream client
- Sampling (LLM call) with simple `RequestParams`
- Prompts and Resources registered on the FastMCP server

## Run the server

```bash
uv run server.py
```

This starts an SSE server at `http://127.0.0.1:8000/sse`.

## Try it with the minimal client

```bash
uv run client.py
```

The client connects over SSE, sets logging level, and exercises tools:

- `finder_tool` — Agent + LLM + MCP servers
- `notify` — logging/notifications
- `sample_haiku` — LLM sampling
- `confirm_action` — elicitation prompt

## Prompts & Resources

The server registers a couple of demo resources and a simple prompt:

- Resources:
  - `demo://docs/readme` — sample README content
  - `demo://{city}/weather` — simple weather string
- Prompt:
  - `echo(message: str)` — returns `Prompt: {message}`

You can use any MCP client capable of listing resources/prompts to explore these.

## Configuration

Put your API keys in `mcp_agent.secrets.yaml` or environment variables
(`OPENAI_API_KEY`, etc.). The server uses the MCP app configuration
(`mcp_agent.config.yaml`) for MCP servers and provider defaults.

## Deploy to Cloud (optional)

1. Set API keys in `mcp_agent.secrets.yaml`.

2. From this directory:

```bash
uv run mcp-agent deploy reference-server
```

Use the URL (append `/sse`) in an MCP client and include your mcp-agent API key as a bearer token if required.
