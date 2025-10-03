Agent Factory

This folder shows how to define agents and compose powerful LLM workflows using the functional helpers in [`factory.py`](https://github.com/lastmile-ai/mcp-agent/blob/main/src/mcp_agent/workflows/factory.py).

What's included

- `agents.yaml`: simple YAML agents
- `mcp_agent.config.yaml`: enables auto-loading subagents from inline definitions and directories
- `mcp_agent.secrets.yaml.example`: template for API keys
- `load_and_route.py`: load agents and route via an LLM
- `auto_loaded_subagents.py`: discover subagents from config (Claude-style markdown and others)
- `orchestrator_demo.py`: orchestrator-workers pattern
- `parallel_demo.py`: parallel fan-out/fan-in pattern

### Quick start

1. Copy secrets

```bash
cp examples/basic/agent_factory/mcp_agent.secrets.yaml.example examples/basic/agent_factory/mcp_agent.secrets.yaml
# Fill in your provider API keys (OpenAI/Anthropic/etc.)
```

2. Run an example

```bash
uv run examples/basic/agent_factory/load_and_route.py
uv run examples/basic/agent_factory/orchestrator_demo.py
uv run examples/basic/agent_factory/parallel_demo.py
uv run examples/basic/agent_factory/auto_loaded_subagents.py
```

3. Try auto-loaded subagents

- Add markdown agents to `.claude/agents` or `.mcp-agent/agents` in the project or home directory, or use the inline examples in `mcp_agent.config.yaml`.

Tip: Examples resolve paths using `Path(__file__).resolve().parent`, so they work regardless of your current working directory.

---

## Composing workflows together (detailed example)

Below is a realistic composition that:

- Loads agents from `agents.yaml`
- Builds a router that picks the right specialist (finder/coder)
- Runs a parallel fan-out (router as a worker + two more workers + a fallback function)
- Aggregates with a fan-in LLM
- If needed, passes the result through an evaluator–optimizer loop for quality

```python
import asyncio
from pathlib import Path

from mcp_agent.app import MCPApp
from mcp_agent.workflows.factory import (
    AgentSpec,
    load_agent_specs_from_file,
    create_llm,
    create_router_llm,
    create_parallel_llm,
    create_evaluator_optimizer_llm,
)


async def main():
    async with MCPApp(name="composed_workflows").run() as agent_app:
        context = agent_app.context
        # Point filesystem to the repo root (handy for demos)
        if "filesystem" in context.config.mcp.servers:
            context.config.mcp.servers["filesystem"].args.extend(["."])

        # 1) Load AgentSpecs
        agents_path = Path(__file__).resolve().parent / "agents.yaml"
        specs = load_agent_specs_from_file(str(agents_path), context=context)

        # 2) Compose a Router over our agents + servers
        router = await create_router_llm(
            server_names=["filesystem", "fetch"],
            agents=specs,  # finder, coder from agents.yaml
            provider="openai",
            context=context,
        )

        # 3) Create a fan-in LLM that will aggregate results from parallel workers
        aggregator_llm = create_llm(
            agent_name="aggregator",
            provider="openai",
            model="gpt-4o-mini",
            context=context,
        )

        # 4) Build a parallel workflow where the Router itself participates as a worker,
        #    alongside two other workers and a fallback function
        parallel = create_parallel_llm(
            fan_in=aggregator_llm,
            fan_out=[
                # Use one AugmentedLLM workflow (router) as a worker inside another workflow (parallel)
                router,
                create_llm(
                    agent_name="worker1",
                    provider="openai",
                    model="gpt-4o-mini",
                    context=context,
                ),
                AgentSpec(
                    name="worker2",
                    server_names=["filesystem"],
                    instruction="Read files and summarize",
                ),
                # Functions in fan_out must return a list of messages
                lambda _: ["fallback function output if LLMs fail"],
            ],
            provider="openai",
            context=context,
        )

        # 5) Evaluate/Optimize step to polish the final output (optional)
        optimizer = create_llm(
            agent_name="writer",
            provider="openai",
            model="gpt-4o-mini",
            context=context,
        )
        reviewer = create_llm(
            agent_name="reviewer",
            provider="anthropic",
            model="claude-3-5-sonnet-latest",
            context=context,
        )
        evo = create_evaluator_optimizer_llm(
            optimizer=optimizer,
            evaluator=reviewer,
            min_rating=4,
            max_refinements=2,
            context=context,
        )

        # Execution pipeline
        user_request = "Find README, summarize it, and list top three important files."

        # Fan-out with multiple attempts/perspectives (including the router), then aggregate
        aggregated = await parallel.generate_str(user_request)

        # Polish until high quality
        final_answer = await evo.generate_str(aggregated)
        print("\nFinal Answer:\n", final_answer)


if __name__ == "__main__":
    asyncio.run(main())
```

Notes

- Each stage is independently useful; together they model real tasks: identify → gather/compare → synthesize → polish.
- You can replace providers/models at each step.
- Replace the fallback function with a deterministic checker or a lightweight heuristic if desired.

---

## Core ideas

- **AgentSpec**: A declarative specification for an agent (name, instruction, `server_names`, optional functions). It is the portable format used in config and files.
- **AugmentedLLM**: The core runtime abstraction that executes LLM calls and tools via an underlying `Agent`.
- **Router extends AugmentedLLM**: You can call `router.generate*` and it will route and delegate to the right agent automatically.
- **Factory helpers**: Simple functions to create agents/LLMs/workflows in a few lines.

---

## Define agents in config and files

There are three main ways to define agents:

1. Inline config definitions (highest precedence)

```yaml
agents:
  enabled: true
  search_paths:
    - ".claude/agents"
    - "~/.claude/agents"
    - ".mcp-agent/agents"
    - "~/.mcp-agent/agents"
  pattern: "**/*.*"
  definitions:
    - name: inline-coder
      instruction: |
        Senior software engineer. Proactively read and edit files.
        Prefer small, safe changes and explain briefly.
      servers: [filesystem]
    - name: inline-researcher
      instruction: |
        Web research specialist. Use fetch tools to gather and summarize information.
      servers: [fetch]
```

2. YAML/JSON files containing `AgentSpec`s (see `agents.yaml`)

```yaml
agents:
  - name: finder
    instruction: You can read files and fetch URLs
    server_names: [filesystem, fetch]
  - name: coder
    instruction: You can inspect and modify code files in the repository
    server_names: [filesystem]
```

3. Claude-style Markdown subagents

```markdown
---
name: code-reviewer
description: Expert code reviewer, use proactively
tools: filesystem, fetch
---

Review code rigorously. Provide findings by priority.
```

Note: `tools:` are currently mapped to `server_names` for convenience.

Precedence & discovery

- On startup, the app searches for agent files from `search_paths` (earlier entries win) and merges inline `definitions` last to overwrite duplicates by name.
- Config files are discovered in current/parent directories and in `.mcp-agent/`, with a home fallback `~/.mcp-agent/`.

---

## Factory helpers (building blocks)

All helpers live in `mcp_agent.workflows.factory`.

### create_llm

Create an `AugmentedLLM` from an `AgentSpec`.

```python
from mcp_agent.workflows.factory import create_llm

llm = create_llm(
    agent_name="reader",
    server_names=["filesystem"],
    instruction="Read files and summarize",
    provider="openai",       # or anthropic, azure, google, bedrock, ollama
    model="gpt-4o-mini",     # or "openai:gpt-4o-mini" or a ModelPreferences
    context=context,
)
print(await llm.generate_str("Summarize README.md"))
```

### create_router_llm / create_router_embedding

Route to the most appropriate destination (server, agent, or function). As an `AugmentedLLM`, `router.generate*` delegates to the selected agent.

```python
from mcp_agent.workflows.factory import create_router_llm

router = await create_router_llm(
    server_names=["filesystem", "fetch"],
    agents=specs_or_loaded_subagents,  # AgentSpec | Agent | AugmentedLLM
    functions=[callable_fn],
    provider="openai",
    context=context,
)
print(await router.generate_str("Find the README and summarize it"))
```

Use `create_router_embedding` to route via embeddings (OpenAI or Cohere).

### create_orchestrator

Planner–workers–synthesizer pattern (fast, simple).

```python
from mcp_agent.workflows.factory import create_orchestrator
from mcp.types import ModelPreferences

orch = create_orchestrator(
    available_agents=[planner_llm, *specs],
    provider="anthropic",
    model=ModelPreferences(costPriority=0.2, speedPriority=0.3, intelligencePriority=0.5),
    context=context,
)
print(await orch.generate_str("Summarize key components in this repo"))
```

### create_deep_orchestrator

Deep research orchestrator for long-horizon tasks (planning, dependency resolution, knowledge accumulation, policy-driven control). Prefer when tasks are complex and iterative.

```python
from mcp_agent.workflows.factory import create_deep_orchestrator

deep = create_deep_orchestrator(
    available_agents=specs,
    provider="openai",
    model="gpt-4o-mini",
    context=context,
)
```

### create_parallel_llm

Fan-out work to multiple agents/LLMs/functions, then fan-in to aggregate.

```python
from mcp_agent.workflows.factory import create_parallel_llm, create_llm, AgentSpec

fan_in_llm = create_llm(agent_name="aggregator", provider="openai", model="gpt-4o-mini", context=context)

par = create_parallel_llm(
    fan_in=fan_in_llm,
    fan_out=[
        create_llm(agent_name="worker1", provider="openai", model="gpt-4o-mini", context=context),
        AgentSpec(name="worker2", server_names=["filesystem"], instruction="Read files and summarize"),
        # Functions must return a list of messages (not a single string)
        lambda _: ["fallback function output"],
    ],
    provider="openai",
    context=context,
)
print(await par.generate_str("Summarize README and list top files"))
```

### create_evaluator_optimizer_llm

Generate → evaluate → refine until acceptable quality.

```python
from mcp_agent.workflows.factory import create_evaluator_optimizer_llm, create_llm

optimizer = create_llm(agent_name="writer", provider="openai", model="gpt-4o-mini", context=context)
evaluator = create_llm(agent_name="reviewer", provider="anthropic", model="claude-3-5-sonnet-latest", context=context)

evo = create_evaluator_optimizer_llm(
    optimizer=optimizer,
    evaluator=evaluator,
    min_rating=4,
    max_refinements=3,
    context=context,
)
print(await evo.generate_str("Draft a concise project overview"))
```

### create_swarm

Tool-using, agent-to-agent handoff style with MCP servers.

```python
from mcp_agent.workflows.factory import create_swarm

swarm = create_swarm(
    name="swarm-researcher",
    instruction="Use fetch and filesystem tools to gather and synthesize answers",
    server_names=["fetch", "filesystem"],
    provider="openai",
    context=context,
)
```

### Intent classifiers

Classify user intent with an LLM or embeddings.

```python
from mcp_agent.workflows.factory import create_intent_classifier_llm
from mcp_agent.workflows.intent_classifier.intent_classifier_base import Intent

intents = [
  Intent(key="search", description="Web search and summarize"),
  Intent(key="code", description="Read or modify local code files"),
]
clf = await create_intent_classifier_llm(intents=intents, provider="openai", context=context)
print(await clf.classify("Open the README and summarize it"))
```

---

## Loading AgentSpec(s)

Programmatic loaders are available when you want to work with files directly:

```python
from pathlib import Path
from mcp_agent.workflows.factory import (
  load_agent_specs_from_text,
  load_agent_specs_from_file,
  load_agent_specs_from_dir,
)

specs = load_agent_specs_from_file(str(Path(__file__).parent / "agents.yaml"), context=context)
specs_from_dir = load_agent_specs_from_dir(".mcp-agent/agents", context=context)
```

At runtime, any auto-discovered agents are available at:

```python
loaded = context.loaded_subagents  # List[AgentSpec]
```

---

## MCP convenience on AugmentedLLM

Any `AugmentedLLM` exposes MCP helpers via its underlying `Agent`:

```python
await llm.list_tools(server_name="filesystem")
await llm.list_resources(server_name="filesystem")
await llm.read_resource("file://README.md", server_name="filesystem")
await llm.list_prompts(server_name="some-server")
await llm.get_prompt("my-prompt", server_name="some-server")
```

---

## Tips & troubleshooting

- Model selection: pass a string (e.g., `"openai:gpt-4o-mini"`) or a `ModelPreferences` and the factory will resolve an appropriate model.
- Config discovery order: for each directory up from CWD, we check `<dir>/<filename>` and `<dir>/.mcp-agent/<filename>`, then fall back to `~/.mcp-agent/<filename>`.
- Path errors: resolve example file paths with `Path(__file__).resolve().parent`.
- Parallel functions: when using `create_parallel_llm`, ensure function fan-out returns a list of messages for `.generate` workflows.

---

## What to read next

- `src/mcp_agent/workflows/factory.py` for all helpers and supported providers
- `examples/basic/agent_factory/*.py` for runnable examples
- `schema/mcp-agent.config.schema.json` for the `AgentSpec` and `agents:` config schema
