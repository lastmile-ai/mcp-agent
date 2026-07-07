# Persistent Memory Agent

Cross-session memory for mcp-agent using [Dakera](https://dakera.ai) MCP — a
self-hosted, decay-weighted vector memory server. Directly addresses the
long-term memory feature request in [#12](https://github.com/lastmile-ai/mcp-agent/issues/12).

Unlike a naive "store everything the agent said" loop, this example models
memory as a **project-continuity layer**: only *promoted*, *typed* facts enter
long-term memory, and they are retrieved deliberately by scope — not as a
semantic soup of every message ever exchanged.

## The three memory tiers

| Tier | What it holds | Storage | Survives restart? | Tools |
|------|---------------|---------|-------------------|-------|
| Working context | Current in-process state | mcp-agent `Context` | No | Built-in |
| Session trace | What happened this run (auditable) | Dakera session | Yes | `dakera_session_start` / `dakera_session_end` |
| Project memory | Durable, promoted, typed facts | Dakera long-term index | Yes | `dakera_store` / `dakera_batch_recall` / `dakera_recall` |

## The memory contract

The core idea (see [#713](https://github.com/lastmile-ai/mcp-agent/issues/713)):
`dakera_store` should not become a transcript dump. The agent only **promotes**
durable facts, and each record is tagged so it can be scoped and filtered later:

```text
type:<decision | convention | failed_path | bug_fix | open_question>
project:<scope>                 e.g. project:multi-agent-frameworks
status:<accepted | candidate | superseded>
```

`accepted` facts are stored with high importance (0.8–0.9) so they survive
decay; everything else stays a `candidate` until confirmed.

## What the example demonstrates

The script (`main.py`) runs three phases that map onto the tiers in #12:

1. **Research & promote** — the agent loads prior accepted facts, researches
   the gap, and stores only promotable, typed records.
2. **Scope-filtered recall** — a *fresh* agent (simulating a restart) uses
   `dakera_batch_recall` filtered by `project:…` + `status:accepted`, so it
   pulls back only durable facts for this project. This is the **scope-based
   retrieval** from #12.
3. **Entity / knowledge-graph memory** — `dakera_extract_entities` +
   `dakera_knowledge_graph` turn the stored prose into a queryable entity
   graph. This is the **graph/entity memory** tier from #12.

Re-run the whole script to see continuity: Phase 1 recalls what the previous
run stored before adding anything new.

## Prerequisites

```bash
# 1. Start Dakera locally (self-hosted server + MinIO object store) via docker-compose.
#    The server needs the object store the compose provisions, so use dakera-deploy
#    rather than a bare `docker run`.
git clone https://github.com/dakera-ai/dakera-deploy
cd dakera-deploy && docker compose up -d   # REST API on http://localhost:3000

# 2. Verify the MCP server starts
npx @dakera-ai/dakera-mcp --help

# 3. Set env vars (API key is the one configured in dakera-deploy, e.g. dk-...)
export DAKERA_API_URL=http://localhost:3000
export DAKERA_API_KEY=dk-...
export ANTHROPIC_API_KEY=your-key
```

## Run

```bash
cd examples/usecases/persistent_memory_agent

# First run: researches and promotes typed facts
python main.py

# Second run: fresh agents recall prior accepted facts by scope
python main.py
```

## Dakera MCP tools used here

| Tool | Purpose | Used in |
|------|---------|---------|
| `dakera_session_start` / `dakera_session_end` | Bracket the session trace | All phases |
| `dakera_store` | Promote a typed, scoped fact | Phase 1 |
| `dakera_batch_recall` | Scope-filtered retrieval by tags | Phases 2–3 |
| `dakera_recall` | Semantic (decay-weighted) recall | Optional |
| `dakera_extract_entities` | NER → knowledge-graph entities | Phase 3 |
| `dakera_knowledge_graph` | Query entity relationships | Phase 3 |

Other tools the server exposes (not needed for this example): `dakera_search`
(hybrid BM25 + vector), `dakera_session_memories`, `dakera_forget`,
`dakera_consolidate`, `dakera_memory_get`, `dakera_memory_update`,
`dakera_memory_feedback`.

## Config

See `mcp_agent.config.yaml`. The Dakera MCP server runs via
`npx @dakera-ai/dakera-mcp`; `DAKERA_API_URL` / `DAKERA_API_KEY` are read from
the environment.
