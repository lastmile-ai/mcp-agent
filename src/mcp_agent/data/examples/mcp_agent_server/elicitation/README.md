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

