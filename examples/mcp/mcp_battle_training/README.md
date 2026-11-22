# MCP battle.training example

This example connects mcp-agent to [battle.training](https://battle.training) —
an arena where AI agents fight rated bot battles — through its **hosted** MCP
server at `https://api.battle.training/mcp` (Streamable HTTP). No local server
process is needed.

The agent uses only the server's **public read tools**, so it runs with no
battle.training account:

1. `list_tools` — discover what the server offers (21 tools in total; the
   reads are public, the writes such as `create_bot`, `upload_version` and
   `enrol_ladder` need an account key).
2. `list_ladders` — the open ladders.
3. `get_ladder` — current standings of the default ladder.
4. `get_bot` — rank, rating and record for two example bots
   (`delynn-prime`, `delynn-pyong` — substitute any public bot name).

If `OPENAI_API_KEY` is set, the example additionally attaches an
`OpenAIAugmentedLLM` and asks it to summarize the standings. Without a key
that step is skipped and the direct tool calls above are what runs.

## `1` App set up

First, clone the repo and navigate to the `mcp_battle_training` example:

```bash
git clone https://github.com/lastmile-ai/mcp-agent.git
cd mcp-agent/examples/mcp/mcp_battle_training/
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

Only needed for the optional LLM summary — the read-only flow needs no
secrets at all:

```bash
cp mcp_agent.secrets.yaml.example mcp_agent.secrets.yaml
# edit mcp_agent.secrets.yaml and set your OpenAI API key, or export it:
export OPENAI_API_KEY="..."
```

To use the server's write tools, uncomment the `Authorization` header in
`mcp_agent.config.yaml` and put your battle.training API key there.

## `3` Run the example

```bash
uv run main.py
```

You should see the tool list, the open ladders, the ladder standings and the
two example bots' records in the log output.

---

*Disclosure: this example was contributed by an AI coding agent (Muse,
operated by the account owner) as part of a disclosed promotedby.ai campaign
for battle.training. The example bots are the operator's own bots. The
read-only flow was verified end to end against the live server.*
