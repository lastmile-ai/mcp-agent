# Streamlit MCP Agent example

This Streamlit example shows a "finder" Agent which has access to the 'fetch' and 'filesystem' MCP servers.

You can ask it information about local files or URLs, and it will make the determination on what to use at what time to satisfy the request.

<img src="https://github.com/user-attachments/assets/7ad27d23-9ed6-4e0e-ba7f-2d3b0afef847" height="512">

---

```plaintext
┌───────────┐      ┌──────────┐      ┌──────────────┐
│ Streamlit │─────▶│  Finder  │──┬──▶│  Fetch       │
│ App       │      │  Agent   │  │   │  MCP Server  │
└───────────┘      └──────────┘  │   └──────────────┘
                                 │   ┌──────────────┐
                                 └──▶│  Filesystem  │
                                     │  MCP Server  │
                                     └──────────────┘
```

## `1` App set up

First, clone the repo and navigate to the Streamlit MCP Agent example:

```bash
git clone https://github.com/lastmile-ai/mcp-agent.git
cd mcp-agent/examples/usecase/streamlit_mcp_basic_agent
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

Then open `mcp_agent.secrets.yaml` and add your api key for your preferred LLM.

## `3` Run locally

To run this example:

With uv:

```bash
uv run streamlit run main.py
```
