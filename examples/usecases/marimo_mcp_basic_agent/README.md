# marimo MCP Agent example

This example [marimo](https://github.com/marimo-team/marimo) notebook shows a
"finder" Agent which has access to the 'fetch' and 'filesystem' MCP servers.

You can ask it information about local files or URLs, and it will make the
determination on what to use at what time to satisfy the request.

https://github.com/user-attachments/assets/3396d0e8-94ab-4997-9370-09124db8cdea

---

```plaintext
┌──────────┐      ┌──────────┐      ┌──────────────┐
│ marimo   │─────▶│  Finder  │──┬──▶│  Fetch       │
│ notebook │      │  Agent   │  │   │  MCP Server  │
└──────────┘      └──────────┘  │   └──────────────┘
                                │   ┌──────────────┐
                                └──▶│  Filesystem  │
                                    │  MCP Server  │
                                    └──────────────┘
```

## `1` App set up

First, clone the repo and navigate to the marimo agent example:

```bash
git clone https://github.com/lastmile-ai/mcp-agent.git
cd mcp-agent/examples/usecases/marimo_mcp_basic_agent
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

Next modify `mcp_agent.config.yaml` to include directories to which
you'd like to give the agent access.

## `2` Run locally

Then run with:

```bash
OPENAI_API_KEY=<your-api-key> uvx marimo edit --sandbox notebook.py
```

To serve as a read-only app, use

```bash
OPENAI_API_KEY=<your-api-key> uvx marimo run --sandbox notebook.py
```
