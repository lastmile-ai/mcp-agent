# Notifications Server

Minimal server demonstrating logging and non-logging notifications.

## Run

```bash
uv run server.py
```

Connect with the minimal client:

```bash
uv run client.py
```

Tools:

- `notify(message: str, level: str='info')` — forwards logs to the upstream client.
- `notify_progress(progress: float, message: Optional[str])` — sends a progress notification.

These are best-effort and non-blocking for the server.

## Deploy to Cloud (optional)

1. Set API keys in `mcp_agent.secrets.yaml` as needed.

2. Deploy from this directory:

```bash
uv run mcp-agent deploy notifications-demo
```

Use the returned URL with `/sse` in an MCP client. Set the Bearer token in the header to your mcp-agent API key.
