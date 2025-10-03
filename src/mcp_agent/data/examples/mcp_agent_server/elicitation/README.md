# Elicitation Server

Minimal server demonstrating user confirmation via elicitation.

## Run

```bash
uv run server.py
```

Connect with the minimal client:

```bash
uv run client.py
```

Tools:

- `confirm_action(action: str)` — prompts the user (via upstream client) to accept or decline.

This example uses console handlers for local testing. In an MCP client UI, the prompt will be displayed to the user.

## Deploy to Cloud (optional)

1. Set your API keys in `mcp_agent.secrets.yaml`.

2. From this directory, deploy:

```bash
uv run mcp-agent deploy elicitation-example
```

You’ll receive an app ID and a URL. Use the URL with an MCP client (e.g., MCP Inspector) and append `/sse` to the end. Set the Bearer token in the header to your mcp-agent API key.
