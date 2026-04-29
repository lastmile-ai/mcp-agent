# Lore Context Memory-Enhanced Research Agent

A research assistant agent that uses [Lore Context](https://lore.cm) as a
persistent memory backend.  Research findings are stored in Lore across
multiple sessions, then recalled semantically when answering new questions.

This example fills the **cross-session memory gap** — mcp-agent's built-in
`SimpleMemory` is in-process only and lost on restart.  Lore Context gives
the agent durable, searchable, long-term memory.

```plaintext
┌───────────────┐      ┌──────────────────────┐
│ Lore Research │──┬──▶│  Lore Context        │
│    Agent      │  │   │  MCP Server          │
└───────────────┘  │   │  (memory_search,     │
                   │   │   memory_write,      │
                   │   │   context_query …)   │
                   │   └──────────────────────┘
                   │
                   └──▶ LLM (OpenAI GPT-4o)
```

## `1` App set up

First, clone the repo and navigate to this example:

```bash
git clone https://github.com/lastmile-ai/mcp-agent.git
cd mcp-agent/examples/usecases/mcp_lore_memory_agent
```

Install `uv` (if you don't have it):

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

Copy and configure your secrets:

```bash
cp mcp_agent.secrets.yaml.example mcp_agent.secrets.yaml
```

Then open `mcp_agent.secrets.yaml` and fill in:

- **`LORE_API_KEY`** — your [Lore Context](https://lore.cm) API key
- **`openai.api_key`** — your OpenAI API key

You can also set `LORE_API_KEY` as an environment variable:

```bash
export LORE_API_KEY="your_key_here"
```

## `3` Run locally

Run the memory-enhanced research agent:

```bash
uv run main.py
```

The agent will:

1. **Session 1** — Research quantum computing, store findings in Lore
2. **Session 2** — Research quantum error correction, recall prior Lore
   context, store new findings
3. **Session 3** — Synthesize all stored knowledge into a report
4. **Export** — List all memories stored in Lore

## `4` What it demonstrates

| Capability | How it's shown |
|------------|----------------|
| **Store findings** | Agent uses `lore_memory_write` after each research task |
| **Recall past context** | Agent searches Lore with `lore_memory_search` before new research |
| **Cross-session memory** | Findings from Session 1 are available in Sessions 2 and 3 |
| **Semantic search** | Lore's vector search surfaces relevant memories by meaning |
| **Knowledge accumulation** | Each session adds to a growing knowledge base |

## `5` Deploy (optional)

For durable execution with Temporal, change the config:

```yaml
execution_engine: temporal
```

See the [Temporal examples](../../temporal/) for more details.
