# battle.training Arena Agent

This example connects an `mcp-agent` agent to the remote Streamable HTTP MCP server at [battle.training](https://battle.training/) (`https://api.battle.training/mcp`).

## What it demonstrates

- Connecting to a stateless Streamable HTTP MCP endpoint via `mcp-agent`
- Discovering arena tools (`get_started`, `get_rules`, `list_ladders`, `get_ladder`, `get_cup`, `get_bot`)
- Optionally running an LLM-driven commander loop to inspect ladder standings and analyze bot match statistics

## Setup

```bash
cd examples/usecases/battle_training_arena_agent
pip install -r requirements.txt
cp mcp_agent.secrets.yaml.example mcp_agent.secrets.yaml
# Optional: add your OpenAI API key to mcp_agent.secrets.yaml for --llm mode
```

## Usage

### 1. Read-only MCP tool smoke check (no API key required)

```bash
python main.py
```

### 2. Full LLM analysis mode

```bash
python main.py --llm --bot nmore-vanguard
```
