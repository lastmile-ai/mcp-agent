# MCP Ollama Agent example

This example shows a "finder" Agent using llama models to access the 'fetch' and 'filesystem' MCP servers.

You can ask it information about local files or URLs, and it will make the determination on what to use at what time to satisfy the request.

![GPT-OSS-Warp](https://github.com/user-attachments/assets/20e0029e-4480-4175-8a27-8ef67697c3fa)

## `1` App set up

First, clone the repo and navigate to the MCP Basic Ollama Agent example:

```bash
git clone https://github.com/lastmile-ai/mcp-agent.git
cd mcp-agent/examples/model_providers/mcp_basic_ollama_agent
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

Make sure you have [Ollama installed](https://ollama.com/download). Then pull the required models for the example:

```bash
ollama pull gpt-oss:20b

ollama run gpt-oss:20b
```

This example uses [OpenAI's gpt-oss-20b](https://openai.com/index/introducing-gpt-oss/).

## `2` Run locally

Then simply run the example:
`uv run main.py`
