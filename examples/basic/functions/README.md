# MCP Functions Agent Example

This example shows a "math" Agent using manually-defined functions to compute simple math results for a user request.

The agent will determine, based on the request, which functions to call and in what order.

<img width="2160" alt="Image" src="https://github.com/user-attachments/assets/14cbfdf4-306f-486b-9ec1-6576acf0aeb7" />

---

```plaintext
┌──────────┐      ┌───────────────────┐
│   Math   │──┬──▶│   add function    │
│   Agent  │  │   └───────────────────┘
└──────────┘  │   ┌───────────────────┐
              └──▶│ multiply function │
                  └───────────────────┘
```

## `1` App set up

First, clone the repo and navigate to the functions example:

```bash
git clone https://github.com/lastmile-ai/mcp-agent.git
cd mcp-agent/examples/basic/functions
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

Then open `mcp_agent.secrets.yaml` and add your api key for your preferred LLM for your MCP servers.

## `3` Run locally

Run your MCP Agent app:

```bash
uv run main.py
```
