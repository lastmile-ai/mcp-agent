<p align="center">
  <a href="https://docs.mcp-agent.com"><img src="https://github.com/user-attachments/assets/c8d059e5-bd56-4ea2-a72d-807fb4897bde" alt="Logo" width="300" /></a>
</p>

<p align="center">
  <em>Build effective agents with Model Context Protocol using simple, composable patterns.</em>

<p align="center">
  <a href="https://github.com/lastmile-ai/mcp-agent/tree/main/examples" target="_blank"><strong>Examples</strong></a>
  |
  <a href="https://docs.mcp-agent.com/mcp-agent-sdk/effective-patterns/overview" target="_blank"><strong>Building Effective Agents</strong></a>
  |
  <a href="https://modelcontextprotocol.io/introduction" target="_blank"><strong>MCP</strong></a>
</p>

<p align="center">
<a href="https://docs.mcp-agent.com"><img src="https://img.shields.io/badge/docs-8F?style=flat&link=https%3A%2F%2Fdocs.mcp-agent.com%2F" /><a/>
<a href="https://pypi.org/project/mcp-agent/"><img src="https://img.shields.io/pypi/v/mcp-agent?color=%2334D058&label=pypi" /></a>
<img alt="Pepy Total Downloads" src="https://img.shields.io/pepy/dt/mcp-agent?label=pypi%20%7C%20downloads"/>
<a href="https://github.com/lastmile-ai/mcp-agent/blob/main/LICENSE"><img src="https://img.shields.io/badge/License-Apache_2.0-blue.svg"/></a>
<a href="https://lmai.link/discord/mcp-agent"><img src="https://img.shields.io/badge/Discord-%235865F2.svg?logo=discord&logoColor=white" alt="discord"/></a>
</p>

<p align="center">
<a href="https://trendshift.io/repositories/13216" target="_blank"><img src="https://trendshift.io/api/badge/repositories/13216" alt="lastmile-ai%2Fmcp-agent | Trendshift" style="width: 250px; height: 55px;" width="250" height="55"/></a>
</p>

## Overview

**`mcp-agent`** is a simple, composable framework to build agents using [Model Context Protocol](https://modelcontextprotocol.io/introduction).

> [!Note]
> mcp-agent's vision is that _MCP is all you need to build agents, and that simple patterns are more robust than complex architectures for shipping high-quality agents_.

`mcp-agent` gives you the following:

1. **Full MCP support**: It _fully_ implements MCP, and handles the pesky business of managing the lifecycle of MCP server connections so you don't have to.
2. **Effective agent patterns**: It implements every pattern described in Anthropic's [Building Effective Agents](https://www.anthropic.com/engineering/building-effective-agents) in a _composable_ way, allowing you to chain these patterns together.
3. **Durable agents**: It works for simple agents and scales to sophisticated workflows built on [Temporal](https://temporal.io/) so you can pause, resume, and recover without any API changes to your agent.

<u>Altogether, this is the simplest and easiest way to build robust agent applications</u>.

We welcome all kinds of [contributions](/CONTRIBUTING.md), feedback and your help in improving this project.

<a id="minimal-example"></a>
**Minimal example**

```python
import asyncio

from mcp_agent.app import MCPApp
from mcp_agent.agents.agent import Agent
from mcp_agent.workflows.llm.augmented_llm_openai import OpenAIAugmentedLLM

app = MCPApp(name="hello_world")

async def main():
    async with app.run():
        agent = Agent(
            name="finder",
            instruction="Use filesystem and fetch to answer questions.",
            server_names=["filesystem", "fetch"],
        )
        async with agent:
            llm = await agent.attach_llm(OpenAIAugmentedLLM)
            answer = await llm.generate_str("Summarize README.md in two sentences.")
            print(answer)


if __name__ == "__main__":
    asyncio.run(main())

# Add your LLM API key to `mcp_agent.secrets.yaml` or set it in env.
# The [Getting Started guide](https://docs.mcp-agent.com/get-started/overview) walks through configuration and secrets in detail.

```

## At a glance

<table>
  <tr>
    <td width="50%" valign="top">
      <h3>Build an Agent</h3>
      <p>Connect LLMs to MCP servers in simple, composable patterns like map-reduce, orchestrator, evaluator-optimizer, router & more.</p>
      <p>
        <a href="https://docs.mcp-agent.com/get-started/overview">Quick Start ↗</a> | 
        <a href="https://docs.mcp-agent.com/mcp-agent-sdk/overview">Docs ↗</a>
      </p>
    </td>
    <td width="50%" valign="top">
      <h3>Create any kind of MCP Server</h3>
      <p>Create MCP servers with a FastMCP-compatible API. You can even expose agents as MCP servers.</p>
      <p>
        <a href="https://docs.mcp-agent.com/mcp-agent-sdk/mcp/agent-as-mcp-server">MCP Agent Server ↗</a> | 
        <a href="https://docs.mcp-agent.com/cloud/use-cases/deploy-chatgpt-apps">🎨 Build a ChatGPT App ↗</a> | 
        <a href="https://github.com/lastmile-ai/mcp-agent/tree/main/examples/mcp_agent_server">Examples ↗</a>
      </p>
    </td>
  </tr>
    <tr>
    <td width="50%" valign="top">
      <h3>Full MCP Support</h3>
      <p><b>Core:</b> Tools ✅ Resources ✅ Prompts ✅ Notifications ✅<br/>
      <b>Advanced</b>: OAuth ✅ Sampling ✅ Elicitation ✅ Roots ✅</p>
      <p>
        <a href="https://github.com/lastmile-ai/mcp-agent/tree/main/examples/mcp">Examples ↗</a> | 
        <a href="https://modelcontextprotocol.io/docs/getting-started/intro">MCP Docs ↗</a>
      </p>
    </td>
    <td width="50%" valign="top">
      <h3>Durable Execution (Temporal)</h3>
      <p>Scales to production workloads using Temporal as the agent runtime backend <i>without any API changes</i>.</p>
      <p>
        <a href="https://docs.mcp-agent.com/mcp-agent-sdk/advanced/durable-agents">Docs ↗</a> | 
        <a href="https://github.com/lastmile-ai/mcp-agent/tree/main/examples/temporal">Examples ↗</a>
      </p>
    </td>
  </tr>
  <tr>
    <td width="50%" valign="top">
      <h3>☁️ Deploy to Cloud</h3>
      <p><b>Beta:</b> Deploy agents yourself, or use <b>mcp-c</b> for a managed agent runtime. All apps are deployed as MCP servers.</p>
      <p>
        <a href="https://www.youtube.com/watch?v=0C4VY-3IVNU">Demo ↗</a> |
        <a href="https://docs.mcp-agent.com/get-started/cloud">Cloud Quickstart ↗</a> | 
        <a href="https://github.com/lastmile-ai/mcp-agent/tree/main/examples/cloud">Examples ↗</a>
      </p>
    </td>
  </tr>
</table>

## Documentation & build with LLMs

mcp-agent's complete documentation is available at **[docs.mcp-agent.com](https://docs.mcp-agent.com)**, including full SDK guides, CLI reference, and advanced patterns. This readme gives a high-level overview to get you started.

- [`llms-full.txt`](https://docs.mcp-agent.com/llms-full.txt): contains entire documentation.
- [`llms.txt`](https://docs.mcp-agent.com/llms.txt): sitemap listing key pages in the docs.
- [docs MCP server](https://docs.mcp-agent.com/mcp)

## Table of Contents

- [Overview](#overview)
- [Minimal example](#minimal-example)
- [Quickstart](#get-started)
- [Why mcp-agent](#why-use-mcp-agent)
- [Core concepts](#core-components)
  - [MCPApp](#mcpapp)
  - [Agents & AgentSpec](#agents--agentspec)
  - [Augmented LLM](#augmented-llm)
  - [Workflows & decorators](#workflows--decorators)
  - [Configuration & secrets](#configuration--secrets)
  - [MCP integration](#mcp-integration)
- [Workflow patterns](#workflow-patterns)
- [CLI reference](#cli-reference)
- [Authentication](#authentication)
- [Advanced](#advanced)
  - [Observability & controls](#observability--controls)
  - [Composing workflows](#composing-workflows)
  - [Durable execution](#durable-execution)
  - [Agent servers](#agent-servers)
  - [Signals & human input](#signals--human-input)
  - [App configuration](#app-configuration)
  - [Icons](#icons)
  - [MCP server management](#mcp-server-management)
- [Cloud deployment](#cloud-deployment)
- [Examples](#examples)
- [FAQs](#faqs)
- [Community & contributions](#contributing)

## Get Started

> [!TIP]
> The CLI is available via `uvx mcp-agent`.
> To get up and running,
> scaffold a project with `uvx mcp-agent init` and deploy with `uvx mcp-agent deploy my-agent`.
>
> You can get up and running in 2 minutes by running these commands:
>
> ```bash
> mkdir hello-mcp-agent && cd hello-mcp-agent
> uvx mcp-agent init
> uv init
> uv add "mcp-agent[openai]"
> # Add openai API key to `mcp_agent.secrets.yaml` or set `OPENAI_API_KEY`
> uv run main.py
> ```

### Installation

We recommend using [uv](https://docs.astral.sh/uv/) to manage your Python projects (`uv init`).

```bash
uv add "mcp-agent"
```

Alternatively:

```bash
pip install mcp-agent
```

Also add optional packages for LLM providers (e.g. `uv add "mcp-agent[openai, anthropic, google, azure, bedrock]"`).

### Quickstart

> [!TIP]
> The [`examples`](/examples) directory has several example applications to get started with.
> To run an example, clone this repo (or generate one with `uvx mcp-agent init --template basic --dir my-first-agent`)
>
> ```bash
> cd examples/basic/mcp_basic_agent # Or any other example
> # Option A: secrets YAML
> # cp mcp_agent.secrets.yaml.example mcp_agent.secrets.yaml && edit mcp_agent.secrets.yaml
> uv run main.py
> ```

Here is a basic "finder" agent that uses the fetch and filesystem servers to look up a file, read a blog and write a tweet. [Example link](./examples/basic/mcp_basic_agent/):

<details open>
<summary>finder_agent.py</summary>

```python
import asyncio
import os

from mcp_agent.app import MCPApp
from mcp_agent.agents.agent import Agent
from mcp_agent.workflows.llm.augmented_llm_openai import OpenAIAugmentedLLM

app = MCPApp(name="hello_world_agent")

async def example_usage():
    async with app.run() as mcp_agent_app:
        logger = mcp_agent_app.logger
        # This agent can read the filesystem or fetch URLs
        finder_agent = Agent(
            name="finder",
            instruction="""You can read local files or fetch URLs.
                Return the requested information when asked.""",
            server_names=["fetch", "filesystem"], # MCP servers this Agent can use
        )

        async with finder_agent:
            # Automatically initializes the MCP servers and adds their tools for LLM use
            tools = await finder_agent.list_tools()
            logger.info(f"Tools available:", data=tools)

            # Attach an OpenAI LLM to the agent (defaults to GPT-4o)
            llm = await finder_agent.attach_llm(OpenAIAugmentedLLM)

            # This will perform a file lookup and read using the filesystem server
            result = await llm.generate_str(
                message="Show me what's in README.md verbatim"
            )
            logger.info(f"README.md contents: {result}")

            # Uses the fetch server to fetch the content from URL
            result = await llm.generate_str(
                message="Print the first two paragraphs from https://www.anthropic.com/research/building-effective-agents"
            )
            logger.info(f"Blog intro: {result}")

            # Multi-turn interactions by default
            result = await llm.generate_str("Summarize that in a 128-char tweet")
            logger.info(f"Tweet: {result}")

if __name__ == "__main__":
    asyncio.run(example_usage())

```

</details>

<details>
<summary>mcp_agent.config.yaml</summary>

```yaml
execution_engine: asyncio
logger:
  transports: [console] # You can use [file, console] for both
  level: debug
  path: "logs/mcp-agent.jsonl" # Used for file transport
  # For dynamic log filenames:
  # path_settings:
  #   path_pattern: "logs/mcp-agent-{unique_id}.jsonl"
  #   unique_id: "timestamp"  # Or "session_id"
  #   timestamp_format: "%Y%m%d_%H%M%S"

mcp:
  servers:
    fetch:
      command: "uvx"
      args: ["mcp-server-fetch"]
    filesystem:
      command: "npx"
      args:
        [
          "-y",
          "@modelcontextprotocol/server-filesystem",
          "<add_your_directories>",
        ]

openai:
  # Secrets (API keys, etc.) are stored in an mcp_agent.secrets.yaml file which can be gitignored
  default_model: gpt-4o
```

</details>

<details>
<summary>Agent output</summary>
<img width="2398" alt="Image" src="https://github.com/user-attachments/assets/eaa60fdf-bcc6-460b-926e-6fa8534e9089" />
</details>

## Why use `mcp-agent`?

There are too many AI frameworks out there already. But `mcp-agent` is the only one that is purpose-built for a shared protocol - [MCP](https://modelcontextprotocol.io/introduction).[mcp-agent](https://docs.mcp-agent.com/get-started/welcome) pairs Anthropic’s Building Effective Agents patterns with a batteries-included MCP runtime so you can focus on behaviour, not boilerplate. Teams pick it because it is:

- **Composable** – every pattern ships as a reusable workflow you can mix and match.
- **MCP-native** – any MCP server (filesystem, fetch, Slack, Jira, FastMCP apps) connects without custom adapters.
- **Production ready** – Temporal-backed durability, structured logging, token accounting, and Cloud deploys are first-class.
- **Pythonic** – a handful of decorators and context managers wire everything together.

Docs: [Welcome to mcp-agent](https://docs.mcp-agent.com/get-started/welcome) • [Effective patterns overview](https://docs.mcp-agent.com/mcp-agent-sdk/effective-patterns/overview).

## Core Components

Every project revolves around a single `MCPApp` runtime that loads configuration, registers agents and MCP servers, and exposes tools/workflows. The [Core Components guide](https://docs.mcp-agent.com/mcp-agent-sdk/overview) walks through these building blocks.

### MCPApp

Initialises configuration, logging, tracing, and the execution engine so everything shares one context.

```python
from mcp_agent.app import MCPApp

app = MCPApp(name="finder_app")

async def main():
    async with app.run() as running_app:
        logger = running_app.logger
        logger.info("App ready", data={"servers": list(running_app.context.server_registry.registry)})
```

Docs: [MCPApp](https://docs.mcp-agent.com/mcp-agent-sdk/core-components/mcpapp) • Example: [`examples/basic/mcp_basic_agent`](./examples/basic/mcp_basic_agent/).

### Agents & AgentSpec

Agents couple instructions with the MCP servers (and optional functions) they may call. `AgentSpec` definitions can be loaded from disk and turned into agents or Augmented LLMs with the factory helpers.

```python
from pathlib import Path
from mcp_agent.agents.agent import Agent
from mcp_agent.workflows.factory import load_agent_specs_from_file

agent = Agent(
    name="researcher",
    instruction="Research topics using web and filesystem access",
    server_names=["fetch", "filesystem"],
)

async with agent:
    tools = await agent.list_tools()

async with app.run() as running_app:
    specs = load_agent_specs_from_file(
        str(Path("examples/basic/agent_factory/agents.yaml")),
        context=running_app.context,
    )
```

Docs: [Agents](https://docs.mcp-agent.com/mcp-agent-sdk/core-components/agents) • [Agent factory helpers](https://docs.mcp-agent.com/mcp-agent-sdk/core-components/agents#agentspec-and-factory-helpers) • Examples: [`examples/basic/agent_factory`](./examples/basic/agent_factory/).

### Augmented LLM

Augmented LLMs wrap provider SDKs with the agent’s tools, memory, and structured output helpers. Attach one to an agent to unlock `generate`, `generate_str`, and `generate_structured`.

```python
from pydantic import BaseModel
from mcp_agent.workflows.llm.augmented_llm import RequestParams
from mcp_agent.workflows.llm.augmented_llm_openai import OpenAIAugmentedLLM

class Summary(BaseModel):
    title: str
    verdict: str

async with agent:
    llm = await agent.attach_llm(OpenAIAugmentedLLM)
    report = await llm.generate_str(
        message="Draft a 3-sentence release note from CHANGELOG.md",
        request_params=RequestParams(maxTokens=400, temperature=0.2),
    )
    structured = await llm.generate_structured(
        message="Return a JSON object with `title` and `verdict` summarising the README.",
        response_model=Summary,
    )
```

Docs: [Augmented LLMs](https://docs.mcp-agent.com/mcp-agent-sdk/core-components/augmented-llm) • Examples: [`examples/basic/mcp_basic_agent`](./examples/basic/mcp_basic_agent/) and the workflow projects listed in [gallery.md](gallery.md#workflow-patterns).

### Workflows & decorators

`MCPApp` decorators convert coroutines into durable workflows and tools. The same annotations work for both `asyncio` and Temporal execution.

```python
from datetime import timedelta
from mcp_agent.executor.workflow import Workflow, WorkflowResult

@app.workflow
class PublishArticle(Workflow[WorkflowResult[str]]):
    @app.workflow_task(schedule_to_close_timeout=timedelta(minutes=5))
    async def draft(self, topic: str) -> str:
        return f"- intro to {topic}\n- highlights\n- next steps"

    @app.workflow_run
    async def run(self, topic: str) -> WorkflowResult[str]:
        outline = await self.draft(topic)
        return WorkflowResult(value=outline)
```

Docs: [Decorator reference](https://docs.mcp-agent.com/reference/decorators) • Examples: [`examples/workflows`](./examples/workflows/).

### Configuration & secrets

Settings load from `mcp_agent.config.yaml`, `mcp_agent.secrets.yaml`, environment variables, and optional preload strings. Keep secrets out of source control.

```yaml
# mcp_agent.config.yaml
execution_engine: asyncio
mcp:
  servers:
    fetch:
      command: "uvx"
      args: ["mcp-server-fetch"]
    filesystem:
      command: "npx"
      args: ["-y", "@modelcontextprotocol/server-filesystem"]
openai:
  default_model: gpt-4o-mini

# mcp_agent.secrets.yaml (gitignored)
openai:
  api_key: "${OPENAI_API_KEY}"
```

Docs: [Configuration reference](https://docs.mcp-agent.com/reference/configuration) • [Specify secrets](https://docs.mcp-agent.com/mcp-agent-sdk/core-components/specify-secrets).

### MCP integration

Connect to existing MCP servers programmatically or aggregate several into one façade.

```python
from mcp_agent.mcp.gen_client import gen_client

async with app.run():
    async with gen_client("filesystem", app.server_registry, context=app.context) as client:
        resources = await client.list_resources()
        app.logger.info("Filesystem resources", data={"uris": [r.uri for r in resources.resources]})
```

Docs: [MCP integration overview](https://docs.mcp-agent.com/mcp/overview) • Examples: [`examples/mcp`](./examples/mcp/).

## Workflow patterns

Key agent patterns are implemented as an `AugmentedLLM`. Use factory helpers to wire them up or inspect the runnable projects listed in [gallery.md](gallery.md#workflow-patterns).

| Pattern               | Helper                                                                          | Summary                                                                                                                                                                                                                                                                                                                                                                                                                                                            | Docs                                                                                                   |
| --------------------- | ------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | ------------------------------------------------------------------------------------------------------ |
| Parallel (Map-Reduce) | `create_parallel_llm(...)`                                                      | Fan-out specialists and fan-in aggregated reports.<br><a href="https://www.anthropic.com/_next/image?url=https%3A%2F%2Fwww-cdn.anthropic.com%2Fimages%2F4zrzovbb%2Fwebsite%2F406bb032ca007fd1624f261af717d70e6ca86286-2401x1000.png&w=3840&q=75"><img src="https://www.anthropic.com/_next/image?url=https%3A%2F%2Fwww-cdn.anthropic.com%2Fimages%2F4zrzovbb%2Fwebsite%2F406bb032ca007fd1624f261af717d70e6ca86286-2401x1000.png&w=3840&q=75" width="260"/></a>     | [Parallel](https://docs.mcp-agent.com/mcp-agent-sdk/effective-patterns/map-reduce)                     |
| Router                | `create_router_llm(...)` / `create_router_embedding(...)`                       | Route requests to the best agent, server, or function.<br><a href="https://www.anthropic.com/_next/image?url=https%3A%2F%2Fwww-cdn.anthropic.com%2Fimages%2F4zrzovbb%2Fwebsite%2F5c0c0e9fe4def0b584c04d37849941da55e5e71c-2401x1000.png&w=3840&q=75"><img src="https://www.anthropic.com/_next/image?url=https%3A%2F%2Fwww-cdn.anthropic.com%2Fimages%2F4zrzovbb%2Fwebsite%2F5c0c0e9fe4def0b584c04d37849941da55e5e71c-2401x1000.png&w=3840&q=75" width="260"/></a> | [Router](https://docs.mcp-agent.com/mcp-agent-sdk/effective-patterns/router)                           |
| Intent classifier     | `create_intent_classifier_llm(...)` / `create_intent_classifier_embedding(...)` | Bucket user input into intents before automation.                                                                                                                                                                                                                                                                                                                                                                                                                  | [Intent classifier](https://docs.mcp-agent.com/mcp-agent-sdk/effective-patterns/intent-classifier)     |
| Orchestrator-workers  | `create_orchestrator(...)`                                                      | Generate plans and coordinate worker agents.<br><a href="https://www.anthropic.com/_next/image?url=https%3A%2F%2Fwww-cdn.anthropic.com%2Fimages%2F4zrzovbb%2Fwebsite%2F8985fc683fae4780fb34eab1365ab78c7e51bc8e-2401x1000.png&w=3840&q=75"><img src="https://www.anthropic.com/_next/image?url=https%3A%2F%2Fwww-cdn.anthropic.com%2Fimages%2F4zrzovbb%2Fwebsite%2F8985fc683fae4780fb34eab1365ab78c7e51bc8e-2401x1000.png&w=3840&q=75" width="260"/></a>           | [Planner](https://docs.mcp-agent.com/mcp-agent-sdk/effective-patterns/planner)                         |
| Deep research         | `create_deep_orchestrator(...)`                                                 | Long-horizon research with knowledge extraction and policy checks.                                                                                                                                                                                                                                                                                                                                                                                                 | [Deep research](https://docs.mcp-agent.com/mcp-agent-sdk/effective-patterns/deep-research)             |
| Evaluator-optimizer   | `create_evaluator_optimizer_llm(...)`                                           | Iterate until an evaluator approves the result.<br><a href="https://www.anthropic.com/_next/image?url=https%3A%2F%2Fwww-cdn.anthropic.com%2Fimages%2F4zrzovbb%2Fwebsite%2F14f51e6406ccb29e695da48b17017e899a6119c7-2401x1000.png&w=3840&q=75"><img src="https://www.anthropic.com/_next/image?url=https%3A%2F%2Fwww-cdn.anthropic.com%2Fimages%2F4zrzovbb%2Fwebsite%2F14f51e6406ccb29e695da48b17017e899a6119c7-2401x1000.png&w=3840&q=75" width="260"/></a>        | [Evaluator-optimizer](https://docs.mcp-agent.com/mcp-agent-sdk/effective-patterns/evaluator-optimizer) |
| Swarm                 | `create_swarm(...)`                                                             | Multi-agent handoffs compatible with OpenAI Swarm.<br><a href="https://github.com/openai/swarm/blob/main/assets/swarm_diagram.png?raw=true"><img src="https://github.com/openai/swarm/blob/main/assets/swarm_diagram.png?raw=true" width="220"/></a>                                                                                                                                                                                                               | [Swarm](https://docs.mcp-agent.com/mcp-agent-sdk/effective-patterns/swarm)                             |

## Durable execution

Switch `execution_engine` to `temporal` for pause/resume, retries, human input, and durable history—without changing workflow code. Run a worker alongside your app to host activities.

```python
from mcp_agent.executor.temporal import create_temporal_worker_for_app

async with create_temporal_worker_for_app(app) as worker:
    await worker.run()
```

Docs: [Durable agents](https://docs.mcp-agent.com/mcp-agent-sdk/advanced/durable-agents) • [Temporal backend](https://docs.mcp-agent.com/advanced/temporal) • Examples: [`examples/temporal`](./examples/temporal/).

## Agent servers

Expose an `MCPApp` as a standard MCP server so Claude Desktop, Cursor, or custom clients can call your tools and workflows.

```python
from mcp_agent.server import create_mcp_server_for_app

@app.tool
def grade_story(story: str) -> str:
    return "Report..."

if __name__ == "__main__":
    server = create_mcp_server_for_app(app)
    server.run_stdio()
```

Docs: [Agent servers](https://docs.mcp-agent.com/mcp-agent-sdk/mcp/agent-as-mcp-server) • Examples: [`examples/mcp_agent_server`](./examples/mcp_agent_server/).

## CLI reference

`uvx mcp-agent` scaffolds projects, manages secrets, inspects workflows, and deploys to Cloud.

```bash
uvx mcp-agent init --template basic             # Scaffold a new project
uvx mcp-agent deploy my-agent                   # Deploy to mcp-agent Cloud
```

Docs: [CLI reference](https://docs.mcp-agent.com/reference/cli) • [Getting started guides](https://docs.mcp-agent.com/get-started/quickstart).

## Authentication

Load API keys from secrets files or use the built-in OAuth client to fetch and persist tokens for MCP servers.

```yaml
# mcp_agent.config.yaml excerpt
oauth:
  providers:
    github:
      client_id: "${GITHUB_CLIENT_ID}"
      client_secret: "${GITHUB_CLIENT_SECRET}"
      scopes: ["repo", "user"]
```

Docs: [Advanced authentication](https://docs.mcp-agent.com/mcp-agent-sdk/advanced/authentication) • [Server authentication](https://docs.mcp-agent.com/mcp-agent-sdk/mcp/server-authentication) • Examples: [`examples/basic/oauth_basic_agent`](./examples/basic/oauth_basic_agent/).

## Advanced

### Observability & controls

Enable structured logging and OpenTelemetry via configuration, and track token usage programmatically.

```yaml
# mcp_agent.config.yaml
logger:
  transports: [console]
  level: info
otel:
  enabled: true
  exporters:
    - console
```

`TokenCounter` tracks token usage for agents, workflows, and LLM nodes. Attach watchers to stream updates or trigger alerts.

```python
# Inside `async with app.run() as running_app:`
# token_counter lives on the running app context when tracing is enabled.
token_counter = running_app.context.token_counter

class TokenMonitor:
    async def on_token_update(self, node, usage):
        print(f"[{node.name}] total={usage.total_tokens}")

monitor = TokenMonitor()
watch_id = await token_counter.watch(
    callback=monitor.on_token_update,
    node_type="llm",
    threshold=1_000,
    include_subtree=True,
)

await token_counter.unwatch(watch_id)
```

Docs: [Observability](https://docs.mcp-agent.com/mcp-agent-sdk/advanced/observability) • Examples: [`examples/tracing`](./examples/tracing/).

### Composing workflows

Mix and match AgentSpecs to build higher-level workflows using the factory helpers—routers, parallel pipelines, orchestrators, and more.

```python
from mcp_agent.workflows.factory import create_router_llm

# specs are loaded via load_agent_specs_from_file as shown above.
async with app.run() as running_app:
    router = await create_router_llm(
        agents=specs,
        provider="openai",
        context=running_app.context,
    )
```

Docs: [Workflow composition](https://docs.mcp-agent.com/mcp-agent-sdk/advanced/composition) • Examples: [`examples/basic/agent_factory`](./examples/basic/agent_factory/).

### Signals & human input

Pause workflows for approvals or extra data. Temporal stores state durably until an operator resumes the run.

```python
from mcp_agent.human_input.types import HumanInputRequest

response = await self.context.request_human_input(
    HumanInputRequest(
        prompt="Approve the draft?",
        required=True,
        metadata={"workflow_id": self.context.workflow_id},
    )
)
```

Resume with `mcp-agent cloud workflows resume … --payload '{"content": "approve"}'`. Docs: [Deploy agents – human input](https://docs.mcp-agent.com/cloud/use-cases/deploy-agents#human-in-the-loop-patterns) • Examples: [`examples/human_input/temporal`](./examples/human_input/temporal/).

### App configuration

Build `Settings` objects programmatically when you need dynamic config (tests, multi-tenant hosts) instead of YAML files.

```python
from mcp_agent.config import Settings, MCPSettings, MCPServerSettings

settings = Settings(
    execution_engine="asyncio",
    mcp=MCPSettings(
        servers={
            "fetch": MCPServerSettings(command="uvx", args=["mcp-server-fetch"]),
        }
    ),
)
app = MCPApp(name="configured_app", settings=settings)
```

Docs: [Configuring your application](https://docs.mcp-agent.com/mcp-agent-sdk/core-components/configuring-your-application).

### Icons

Add icons to agents and tools so MCP clients that support imagery (Claude Desktop, Cursor) render richer UIs.

```python
from base64 import standard_b64encode
from pathlib import Path
from mcp_agent.icons import Icon

icon_data = standard_b64encode(Path("my-icon.png").read_bytes()).decode()
icon = Icon(src=f"data:image/png;base64,{icon_data}", mimeType="image/png", sizes=["64x64"])

app = MCPApp(name="my_app_with_icon", icons=[icon])

@app.tool(icons=[icon])
async def my_tool() -> str:
    return "Hello with style"
```

Docs: [`MCPApp` icons](https://docs.mcp-agent.com/mcp-agent-sdk/core-components/mcpapp#icons) • Examples: [`examples/mcp_agent_server/asyncio`](./examples/mcp_agent_server/asyncio/).

### MCP server management

Use `MCPAggregator` or `gen_client` to manage MCP server connections and expose combined tool sets.

```python
from mcp_agent.mcp.mcp_aggregator import MCPAggregator

async with MCPAggregator.create(server_names=["fetch", "filesystem"]) as aggregator:
    tools = await aggregator.list_tools()
```

Docs: [Connecting to MCP servers](https://docs.mcp-agent.com/mcp-agent-sdk/core-components/connecting-to-mcp-servers) • Examples: [`examples/basic/mcp_server_aggregator`](./examples/basic/mcp_server_aggregator/).

## Cloud deployment

Deploy to mcp-agent Cloud for managed Temporal execution, secrets, and HTTPS MCP endpoints.

```bash
uvx mcp-agent login
uvx mcp-agent deploy my-agent
uvx mcp-agent cloud apps list
```

Docs: [Cloud overview](https://docs.mcp-agent.com/cloud/overview) • [Deployment quickstart](https://docs.mcp-agent.com/cloud/deployment-quickstart) • Examples: [`examples/cloud`](./examples/cloud/).

## Examples

Browse [gallery.md](gallery.md) for runnable examples, demo videos, and community projects grouped by concept. Every entry cites the docs page and command you need to run it locally.

## FAQs

### What are the core benefits of using mcp-agent?

mcp-agent provides a streamlined approach to building AI agents using capabilities exposed by **MCP** (Model Context Protocol) servers.

MCP is quite low-level, and this framework handles the mechanics of connecting to servers, working with LLMs, handling external signals (like human input) and supporting persistent state via durable execution. That lets you, the developer, focus on the core business logic of your AI application.

Core benefits:

- 🤝 **Interoperability**: ensures that any tool exposed by any number of MCP servers can seamlessly plug in to your agents.
- ⛓️ **Composability & Customizability**: Implements well-defined workflows, but in a composable way that enables compound workflows, and allows full customization across model provider, logging, orchestrator, etc.
- 💻 **Programmatic control flow**: Keeps things simple as developers just write code instead of thinking in graphs, nodes and edges. For branching logic, you write `if` statements. For cycles, use `while` loops.
- 🖐️ **Human Input & Signals**: Supports pausing workflows for external signals, such as human input, which are exposed as tool calls an Agent can make.

### Do you need an MCP client to use mcp-agent?

No, you can use mcp-agent anywhere, since it handles MCPClient creation for you. This allows you to leverage MCP servers outside of MCP hosts like Claude Desktop.

Here's all the ways you can set up your mcp-agent application:

#### MCP-Agent Server

You can expose mcp-agent applications as MCP servers themselves (see [example](./examples/mcp_agent_server)), allowing MCP clients to interface with sophisticated AI workflows using the standard tools API of MCP servers. This is effectively a server-of-servers.

#### MCP Client or Host

You can embed mcp-agent in an MCP client directly to manage the orchestration across multiple MCP servers.

#### Standalone

You can use mcp-agent applications in a standalone fashion (i.e. they aren't part of an MCP client). The [`examples`](/examples/) are all standalone applications.

### How do I deploy to Cloud?

Run `uvx mcp-agent deploy <app-name>` after logging in with `uvx mcp-agent login`. The CLI packages your project, provisions secrets, and exposes an MCP endpoint backed by a durable Temporal runtime. See the [Cloud quickstart](https://docs.mcp-agent.com/get-started/
cloud) for step-by-step screenshots and CLI output.

### Where is the API reference?

Every class, decorator, and CLI command is documented on [docs.mcp-agent.com](https://docs.mcp-agent.com). The [API reference](https://docs.mcp-agent.com/reference) and the [`llms-full.txt`](https://docs.mcp-agent.com/llms-full.txt) are designed so LLMs (or you) can ingest the whole surface area easily.

### Tell me a fun fact

I debated naming this project _silsila_ (سلسلہ), which means chain of events in Urdu. mcp-agent is more matter-of-fact, but there's still an easter egg in the project paying homage to silsila.

## Contributing

We welcome contributions of every size—bug fixes, new examples, docs, or feature requests. Start with [CONTRIBUTING.md](./CONTRIBUTING.md), open a discussion, or drop by [Discord](https://lmai.link/discord/mcp-agent).

mcp-agent would not be possible without the tireless efforts of the many open source contributors. Thank you!

<p align="center">
  <a href="https://github.com/lastmile-ai/mcp-agent/graphs/contributors">
    <img src="https://contrib.rocks/image?repo=lastmile-ai/mcp-agent" alt="Contributor faces" />
  </a>
</p>
