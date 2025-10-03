# Elicitation Example

This MCP Agent app shows an Agent which has access to a "Booking System" MCP server. This example highlights the elicitation feature, where a tool can pause its execution to ask the user for additional information or confirmation before proceeding.

You can ask the agent to book a table, and it will use the booking tool, which in turn will ask you for confirmation.

```plaintext
┌──────────┐      ┌──────────────┐
│  Agent   │──┬──▶│  Booking     │
│          │  │   │  System      │
└──────────┘  │   │  (MCP Server)│
              │   └──────────────┘
              │         │
              │         │ ctx.elicit()
              │         ▼
              │   ┌──────────────┐
              └──▶│    User      │
                  │ (via console)│
                  └──────────────┘
```

## Set up

First, clone the repo and navigate to the elicitation example:

```bash
git clone https://github.com/lastmile-ai/mcp-agent.git
cd mcp-agent/examples/mcp/mcp_elicitation
```

Install `uv` (if you don’t have it):

```bash
pip install uv
```

## Set up api keys

In `mcp_agent.secrets.yaml`, set your OpenAI `api_key`.

## Run locally

```bash
uv run main.py
```

You will be prompted for input after the agent makes the initial tool call.
