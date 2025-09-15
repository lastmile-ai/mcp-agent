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

