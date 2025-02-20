<p align="center">
  <img src="https://github.com/user-attachments/assets/6f4e40c4-dc88-47b6-b965-5856b69416d2" alt="Logo" width="300" />
</p>

<p align="center">
  <em>Build effective agents with Model Context Protocol using simple, composable patterns.</em>

<p align="center">
  <a href="https://github.com/lastmile-ai/mcp-agent/tree/main/examples" target="_blank"><strong>Examples</strong></a>
  |
  <a href="https://www.anthropic.com/research/building-effective-agents" target="_blank"><strong>Building Effective Agents</strong></a>
  |
  <a href="https://modelcontextprotocol.io/introduction" target="_blank"><strong>MCP</strong></a>
</p>

<p align="center">
<a href="https://pypi.org/project/mcp-agent/"><img src="https://img.shields.io/pypi/v/mcp-agent?color=%2334D058&label=pypi" /></a>
<a href="https://github.com/lastmile-ai/mcp-agent/issues"><img src="https://img.shields.io/github/issues-raw/lastmile-ai/mcp-agent" /></a>
<a href="https://lmai.link/discord/mcp-agent"><img src="https://shields.io/discord/1089284610329952357" alt="discord" /></a>
<img alt="Pepy Total Downloads" src="https://img.shields.io/pepy/dt/mcp-agent?label=pypi%20%7C%20downloads"/>
<a href="https://github.com/lastmile-ai/mcp-agent/blob/main/LICENSE"><img src="https://img.shields.io/pypi/l/mcp-agent" /></a>
</p>

## Overview

**`mcp-agent`** is a simple, composable framework to build agents using [Model Context Protocol](https://modelcontextprotocol.io/introduction).

**Inspiration**: Anthropic announced 2 foundational updates for AI application developers:

1. [Model Context Protocol](https://www.anthropic.com/news/model-context-protocol) - a standardized interface to let any software be accessible to AI assistants via MCP servers.
2. [Building Effective Agents](https://www.anthropic.com/research/building-effective-agents) - a seminal writeup on simple, composable patterns for building production-ready AI agents.

`mcp-agent` puts these two foundational pieces into an AI application framework:

1. It handles the pesky business of managing the lifecycle of MCP server connections so you don't have to.
2. It implements every pattern described in Building Effective Agents, and does so in a _composable_ way, allowing you to chain these patterns together.
3. **Bonus**: It implements [OpenAI's Swarm](https://github.com/openai/swarm) pattern for multi-agent orchestration, but in a model-agnostic way.

Altogether, this is the simplest and easiest way to build robust agent applications. Much like MCP, this project is in early development.
We welcome all kinds of [contributions](/CONTRIBUTING.md), feedback and your help in growing this to become a new standard.

## Get Started

We recommend using [uv](https://docs.astral.sh/uv/) to manage your Python projects:

```bash
uv add "mcp-agent"
```

Alternatively:

```bash
pip install mcp-agent
```

### Quickstart

> [!TIP]
> The [`examples`](/examples) directory has several example applications to get started with.
> To run an example, clone this repo, then:
>
> ```bash
> cd examples/mcp_basic_agent # Or any other example
> cp mcp_agent.secrets.yaml.example mcp_agent.secrets.yaml # Update API keys
> uv run main.py
> ```

Here is a basic "finder" agent that uses the fetch and filesystem servers to look up a file, read a blog and write a tweet. [Example link](./examples/mcp_basic_agent/):

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
  type: console
  level: debug

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

## Table of Contents

- [Why use mcp-agent?](#why-use-mcp-agent)
- [Example Applications](#examples)
  - [Claude Desktop](#claude-desktop)
  - [Streamlit](#streamlit)
    - [Gmail Agent](#gmail-agent)
    - [RAG](#simple-rag-chatbot)
  - [Marimo](#marimo)
  - [Python](#python)
    - [Swarm (CLI)](#swarm)
- [Core Concepts](#core-components)
- [Workflows Patterns](#workflows)
  - [Augmented LLM](#augmentedllm)
  - [Parallel](#parallel)
  - [Router](#router)
  - [Intent-Classifier](#intentclassifier)
  - [Orchestrator-Workers](#orchestrator-workers)
  - [Evaluator-Optimizer](#evaluator-optimizer)
  - [OpenAI Swarm](#swarm-1)
- [Advanced](#advanced)
  - [Composing multiple workflows](#composability)
  - [Signaling and Human input](#signaling-and-human-input)
  - [App Config](#app-config)
  - [MCP Server Management](#mcp-server-management)
- [Contributing](#contributing)
- [Roadmap](#roadmap)
- [FAQs](#faqs)

## Why use `mcp-agent`?

There are too many AI frameworks out there already. But `mcp-agent` is the only one that is purpose-built for a shared protocol - [MCP](https://modelcontextprotocol.io/introduction). It is also the most lightweight, and is closer to an agent pattern library than a framework.

As [more services become MCP-aware](https://github.com/punkpeye/awesome-mcp-servers), you can use mcp-agent to build robust and controllable AI agents that can leverage those services out-of-the-box.

## Examples

Before we go into the core concepts of mcp-agent, let's show what you can build with it.

In short, you can build any kind of AI application with mcp-agent: multi-agent collaborative workflows, human-in-the-loop workflows, RAG pipelines and more.

### Claude Desktop

You can integrate mcp-agent apps into MCP clients like Claude Desktop.

#### mcp-agent server

This app wraps an mcp-agent application inside an MCP server, and exposes that server to Claude Desktop.
The app exposes agents and workflows that Claude Desktop can invoke to service of the user's request.

https://github.com/user-attachments/assets/7807cffd-dba7-4f0c-9c70-9482fd7e0699

This demo shows a multi-agent evaluation task where each agent evaluates aspects of an input poem, and
then an aggregator summarizes their findings into a final response.

**Details**: Starting from a user's request over text, the application:

- dynamically defines agents to do the job
- uses the appropriate workflow to orchestrate those agents (in this case the Parallel workflow)

**Link to code**: [examples/mcp_agent_server](./examples/mcp_agent_server)

> [!NOTE]
> Huge thanks to [Jerron Lim (@StreetLamb)](https://github.com/StreetLamb)
> for developing and contributing this example!

### Streamlit

You can deploy mcp-agent apps using Streamlit.

#### Gmail agent

This app is able to perform read and write actions on gmail using text prompts -- i.e. read, delete, send emails, mark as read/unread, etc.
It uses an MCP server for Gmail.

https://github.com/user-attachments/assets/54899cac-de24-4102-bd7e-4b2022c956e3

**Link to code**: [gmail-mcp-server](https://github.com/jasonsum/gmail-mcp-server/blob/add-mcp-agent-streamlit/streamlit_app.py)

> [!NOTE]
> Huge thanks to [Jason Summer (@jasonsum)](https://github.com/jasonsum)
> for developing and contributing this example!

#### Simple RAG Chatbot

This app uses a Qdrant vector database (via an MCP server) to do Q&A over a corpus of text.

https://github.com/user-attachments/assets/f4dcd227-cae9-4a59-aa9e-0eceeb4acaf4

**Link to code**: [examples/streamlit_mcp_rag_agent](./examples/streamlit_mcp_rag_agent/)

> [!NOTE]
> Huge thanks to [Jerron Lim (@StreetLamb)](https://github.com/StreetLamb)
> for developing and contributing this example!

### Marimo

[Marimo](https://github.com/marimo-team/marimo) is a reactive Python notebook that replaces Jupyter and Streamlit.
Here's the "file finder" agent from [Quickstart](#quickstart) implemented in Marimo:

<img src="https://github.com/user-attachments/assets/139a95a5-e3ac-4ea7-9c8f-bad6577e8597" width="400"/>

**Link to code**: [examples/marimo_mcp_basic_agent](./examples/marimo_mcp_basic_agent/)

> [!NOTE]
> Huge thanks to [Akshay Agrawal (@akshayka)](https://github.com/akshayka)
> for developing and contributing this example!

### Python

You can write mcp-agent apps as Python scripts or Jupyter notebooks.

#### Swarm

This example demonstrates a multi-agent setup for handling different customer service requests in an airline context using the Swarm workflow pattern. The agents can triage requests, handle flight modifications, cancellations, and lost baggage cases.

https://github.com/user-attachments/assets/b314d75d-7945-4de6-965b-7f21eb14a8bd

**Link to code**: [examples/workflow_swarm](./examples/workflow_swarm/)

## Core Components

The following are the building blocks of the mcp-agent framework:

- **[MCPApp](./src/mcp_agent/app.py)**: global state and app configuration
- **MCP server management**: [`gen_client`](./src/mcp_agent/mcp/gen_client.py) and [`MCPConnectionManager`](./src/mcp_agent/mcp/mcp_connection_manager.py) to easily connect to MCP servers.
- **[Agent](./src/mcp_agent/agents/agent.py)**: An Agent is an entity that has access to a set of MCP servers and exposes them to an LLM as tool calls. It has a name and purpose (instruction).
- **[AugmentedLLM](./src/mcp_agent/workflows/llm/augmented_llm.py)**: An LLM that is enhanced with tools provided from a collection of MCP servers. Every Workflow pattern described below is an `AugmentedLLM` itself, allowing you to compose and chain them together.

Everything in the framework is a derivative of these core capabilities.

## Workflows

mcp-agent provides implementations for every pattern in Anthropic’s [Building Effective Agents](https://www.anthropic.com/research/building-effective-agents), as well as the OpenAI [Swarm](https://github.com/openai/swarm) pattern.
Each pattern is model-agnostic, and exposed as an `AugmentedLLM`, making everything very composable.

### AugmentedLLM

[AugmentedLLM](./src/mcp_agent/workflows/llm/augmented_llm.py) is an LLM that has access to MCP servers and functions via Agents.

LLM providers implement the AugmentedLLM interface to expose 3 functions:

- `generate`: Generate message(s) given a prompt, possibly over multiple iterations and making tool calls as needed.
- `generate_str`: Calls `generate` and returns result as a string output.
- `generate_structured`: Uses [Instructor](https://github.com/instructor-ai/instructor) to return the generated result as a Pydantic model.

Additionally, `AugmentedLLM` has memory, to keep track of long or short-term history.

<details>
<summary>Example</summary>

```python
from mcp_agent.agents.agent import Agent
from mcp_agent.workflows.llm.augmented_llm_anthropic import AnthropicAugmentedLLM

finder_agent = Agent(
    name="finder",
    instruction="You are an agent with filesystem + fetch access. Return the requested file or URL contents.",
    server_names=["fetch", "filesystem"],
)

async with finder_agent:
   llm = await finder_agent.attach_llm(AnthropicAugmentedLLM)

   result = await llm.generate_str(
      message="Print the first 2 paragraphs of https://www.anthropic.com/research/building-effective-agents",
      # Can override model, tokens and other defaults
   )
   logger.info(f"Result: {result}")

   # Multi-turn conversation
   result = await llm.generate_str(
      message="Summarize those paragraphs in a 128 character tweet",
   )
   logger.info(f"Result: {result}")
```

</details>

### [Parallel](src/mcp_agent/workflows/parallel/parallel_llm.py)

![Parallel workflow (Image credit: Anthropic)](https://www.anthropic.com/_next/image?url=https%3A%2F%2Fwww-cdn.anthropic.com%2Fimages%2F4zrzovbb%2Fwebsite%2F406bb032ca007fd1624f261af717d70e6ca86286-2401x1000.png&w=3840&q=75)

Fan-out tasks to multiple sub-agents and fan-in the results. Each subtask is an AugmentedLLM, as is the overall Parallel workflow, meaning each subtask can optionally be a more complex workflow itself.

> [!NOTE]
>
> **[Link to full example](examples/workflow_parallel/main.py)**

<details>
<summary>Example</summary>

```python
proofreader = Agent(name="proofreader", instruction="Review grammar...")
fact_checker = Agent(name="fact_checker", instruction="Check factual consistency...")
style_enforcer = Agent(name="style_enforcer", instruction="Enforce style guidelines...")

grader = Agent(name="grader", instruction="Combine feedback into a structured report.")

parallel = ParallelLLM(
    fan_in_agent=grader,
    fan_out_agents=[proofreader, fact_checker, style_enforcer],
    llm_factory=OpenAIAugmentedLLM,
)

result = await parallel.generate_str("Student short story submission: ...", RequestParams(model="gpt4-o"))
```

</details>

### [Router](src/mcp_agent/workflows/router/)

![Router workflow (Image credit: Anthropic)](https://www.anthropic.com/_next/image?url=https%3A%2F%2Fwww-cdn.anthropic.com%2Fimages%2F4zrzovbb%2Fwebsite%2F5c0c0e9fe4def0b584c04d37849941da55e5e71c-2401x1000.png&w=3840&q=75)

Given an input, route to the `top_k` most relevant categories. A category can be an Agent, an MCP server or a regular function.

mcp-agent provides several router implementations, including:

- [`EmbeddingRouter`](src/mcp_agent/workflows/router/router_embedding.py): uses embedding models for classification
- [`LLMRouter`](src/mcp_agent/workflows/router/router_llm.py): uses LLMs for classification

> [!NOTE]
>
> **[Link to full example](examples/workflow_router/main.py)**

<details>
<summary>Example</summary>

```python
def print_hello_world:
     print("Hello, world!")

finder_agent = Agent(name="finder", server_names=["fetch", "filesystem"])
writer_agent = Agent(name="writer", server_names=["filesystem"])

llm = OpenAIAugmentedLLM()
router = LLMRouter(
    llm=llm,
    agents=[finder_agent, writer_agent],
    functions=[print_hello_world],
)

results = await router.route( # Also available: route_to_agent, route_to_server
    request="Find and print the contents of README.md verbatim",
    top_k=1
)
chosen_agent = results[0].result
async with chosen_agent:
    ...
```

</details>

### [IntentClassifier](src/mcp_agent/workflows/intent_classifier/)

A close sibling of Router, the Intent Classifier pattern identifies the `top_k` Intents that most closely match a given input.
Just like a Router, mcp-agent provides both an [embedding](src/mcp_agent/workflows/intent_classifier/intent_classifier_embedding.py) and [LLM-based](src/mcp_agent/workflows/intent_classifier/intent_classifier_llm.py) intent classifier.

### [Evaluator-Optimizer](src/mcp_agent/workflows/evaluator_optimizer/evaluator_optimizer.py)

![Evaluator-optimizer workflow (Image credit: Anthropic)](https://www.anthropic.com/_next/image?url=https%3A%2F%2Fwww-cdn.anthropic.com%2Fimages%2F4zrzovbb%2Fwebsite%2F14f51e6406ccb29e695da48b17017e899a6119c7-2401x1000.png&w=3840&q=75)

One LLM (the “optimizer”) refines a response, another (the “evaluator”) critiques it until a response exceeds a quality criteria.

> [!NOTE]
>
> **[Link to full example](examples/workflow_evaluator_optimizer/main.py)**

<details>
<summary>Example</summary>

```python
optimizer = Agent(name="cover_letter_writer", server_names=["fetch"], instruction="Generate a cover letter ...")
evaluator = Agent(name="critiquer", instruction="Evaluate clarity, specificity, relevance...")

llm = EvaluatorOptimizerLLM(
    optimizer=optimizer,
    evaluator=evaluator,
    llm_factory=OpenAIAugmentedLLM,
    min_rating=QualityRating.EXCELLENT, # Keep iterating until the minimum quality bar is reached
)

result = await eo_llm.generate_str("Write a job cover letter for an AI framework developer role at LastMile AI.")
print("Final refined cover letter:", result)
```

</details>

### [Orchestrator-workers](src/mcp_agent/workflows/orchestrator/orchestrator.py)

![Orchestrator workflow (Image credit: Anthropic)](https://www.anthropic.com/_next/image?url=https%3A%2F%2Fwww-cdn.anthropic.com%2Fimages%2F4zrzovbb%2Fwebsite%2F8985fc683fae4780fb34eab1365ab78c7e51bc8e-2401x1000.png&w=3840&q=75)

A higher-level LLM generates a plan, then assigns them to sub-agents, and synthesizes the results.
The Orchestrator workflow automatically parallelizes steps that can be done in parallel, and blocks on dependencies.

> [!NOTE]
>
> **[Link to full example](examples/workflow_orchestrator_worker/main.py)**

<details>
<summary>Example</summary>

```python
finder_agent = Agent(name="finder", server_names=["fetch", "filesystem"])
writer_agent = Agent(name="writer", server_names=["filesystem"])
proofreader = Agent(name="proofreader", ...)
fact_checker = Agent(name="fact_checker", ...)
style_enforcer = Agent(name="style_enforcer", instructions="Use APA style guide from ...", server_names=["fetch"])

orchestrator = Orchestrator(
    llm_factory=AnthropicAugmentedLLM,
    available_agents=[finder_agent, writer_agent, proofreader, fact_checker, style_enforcer],
)

task = "Load short_story.md, evaluate it, produce a graded_report.md with multiple feedback aspects."
result = await orchestrator.generate_str(task, RequestParams(model="gpt-4o"))
print(result)
```

</details>

### [Swarm](src/mcp_agent/workflows/swarm/swarm.py)

OpenAI has an experimental multi-agent pattern called [Swarm](https://github.com/openai/swarm), which we provide a model-agnostic reference implementation for in mcp-agent.

<img src="https://github.com/openai/swarm/blob/main/assets/swarm_diagram.png?raw=true" width=500 />

The mcp-agent Swarm pattern works seamlessly with MCP servers, and is exposed as an `AugmentedLLM`, allowing for composability with other patterns above.

> [!NOTE]
>
> **[Link to full example](examples/workflow_orchestrator_worker/main.py)**

<details>
<summary>Example</summary>

```python
triage_agent = SwarmAgent(...)
flight_mod_agent = SwarmAgent(...)
lost_baggage_agent = SwarmAgent(...)

# The triage agent decides whether to route to flight_mod_agent or lost_baggage_agent
swarm = AnthropicSwarm(agent=triage_agent, context_variables={...})

test_input = "My bag was not delivered!"
result = await swarm.generate_str(test_input)
print("Result:", result)
```

</details>

## Advanced

### Composability

An example of composability is using an [Evaluator-Optimizer](#evaluator-optimizer) workflow as the planner LLM inside
the [Orchestrator](#orchestrator-workers) workflow. Generating a high-quality plan to execute is important for robust behavior, and an evaluator-optimizer can help ensure that.

Doing so is seamless in mcp-agent, because each workflow is implemented as an `AugmentedLLM`.

<details>
<summary>Example</summary>

```python
optimizer = Agent(name="plan_optimizer", server_names=[...], instruction="Generate a plan given an objective ...")
evaluator = Agent(name="plan_evaluator", instruction="Evaluate logic, ordering and precision of plan......")

planner_llm = EvaluatorOptimizerLLM(
    optimizer=optimizer,
    evaluator=evaluator,
    llm_factory=OpenAIAugmentedLLM,
    min_rating=QualityRating.EXCELLENT,
)

orchestrator = Orchestrator(
    llm_factory=AnthropicAugmentedLLM,
    available_agents=[finder_agent, writer_agent, proofreader, fact_checker, style_enforcer],
    planner=planner_llm # It's that simple
)

...
```

</details>

### Signaling and Human Input

**Signaling**: The framework can pause/resume tasks. The agent or LLM might “signal” that it needs user input, so the workflow awaits. A developer may signal during a workflow to seek approval or review before continuing with a workflow.

**Human Input**: If an Agent has a `human_input_callback`, the LLM can call a `__human_input__` tool to request user input mid-workflow.

<details>
<summary>Example</summary>

The [Swarm example](examples/workflow_swarm/main.py) shows this in action.

```python
from mcp_agent.human_input.handler import console_input_callback

lost_baggage = SwarmAgent(
    name="Lost baggage traversal",
    instruction=lambda context_variables: f"""
        {
        FLY_AIR_AGENT_PROMPT.format(
            customer_context=context_variables.get("customer_context", "None"),
            flight_context=context_variables.get("flight_context", "None"),
        )
    }\n Lost baggage policy: policies/lost_baggage_policy.md""",
    functions=[
        escalate_to_agent,
        initiate_baggage_search,
        transfer_to_triage,
        case_resolved,
    ],
    server_names=["fetch", "filesystem"],
    human_input_callback=console_input_callback, # Request input from the console
)
```

</details>

## App Config

Create an [`mcp_agent.config.yaml`](/schema/mcp-agent.config.schema.json) and a gitignored [`mcp_agent.secrets.yaml`](./examples/mcp_basic_agent/mcp_agent.secrets.yaml.example) to define MCP app configuration. This controls logging, execution, LLM provider APIs, and MCP server configuration:

## MCP server management

mcp-agent makes it trivial to connect to MCP servers. Create an [`mcp_agent.config.yaml`](/schema/mcp-agent.config.schema.json) to define server configuration under the `mcp` section:

```yaml
mcp:
  servers:
    fetch:
      command: "uvx"
      args: ["mcp-server-fetch"]
      description: "Fetch content at URLs from the world wide web"
```

### [`gen_client`](src/mcp_agent/mcp/gen_client.py)

Manage the lifecycle of an MCP server within an async context manager:

```python
from mcp_agent.mcp.gen_client import gen_client

async with gen_client("fetch") as fetch_client:
    # Fetch server is initialized and ready to use
    result = await fetch_client.list_tools()

# Fetch server is automatically disconnected/shutdown
```

The gen_client function makes it easy to spin up connections to MCP servers.

### Persistent server connections

In many cases, you want an MCP server to stay online for persistent use (e.g. in a multi-step tool use workflow).
For persistent connections, use:

- [`connect`](<(src/mcp_agent/mcp/gen_client.py)>) and [`disconnect`](src/mcp_agent/mcp/gen_client.py)

```python
from mcp_agent.mcp.gen_client import connect, disconnect

fetch_client = None
try:
     fetch_client = connect("fetch")
     result = await fetch_client.list_tools()
finally:
     disconnect("fetch")
```

- [`MCPConnectionManager`](src/mcp_agent/mcp/mcp_connection_manager.py)
  For even more fine-grained control over server connections, you can use the MCPConnectionManager.

<details>
<summary>Example</summary>
```python
from mcp_agent.context import get_current_context
from mcp_agent.mcp.mcp_connection_manager import MCPConnectionManager

context = get_current_context()
connection_manager = MCPConnectionManager(context.server_registry)

async with connection_manager:
fetch_client = await connection_manager.get_server("fetch") # Initializes fetch server
result = fetch_client.list_tool()
fetch_client2 = await connection_manager.get_server("fetch") # Reuses same server connection

# All servers managed by connection manager are automatically disconnected/shut down

````

</details>

### MCP Server Aggregator

[`MCPAggregator`](src/mcp_agent/mcp/mcp_aggregator.py) acts as a "server-of-servers".
It provides a single MCP server interface for interacting with multiple MCP servers.
This allows you to expose tools from multiple servers to LLM applications.

<details>
<summary>Example</summary>

```python
from mcp_agent.mcp.mcp_aggregator import MCPAggregator

aggregator = await MCPAggregator.create(server_names=["fetch", "filesystem"])

async with aggregator:
   # combined list of tools exposed by 'fetch' and 'filesystem' servers
   tools = await aggregator.list_tools()

   # namespacing -- invokes the 'fetch' server to call the 'fetch' tool
   fetch_result = await aggregator.call_tool(name="fetch-fetch", arguments={"url": "https://www.anthropic.com/research/building-effective-agents"})

   # no namespacing -- first server in the aggregator exposing that tool wins
   read_file_result = await aggregator.call_tool(name="read_file", arguments={})
````

</details>

## Contributing

We welcome any and all kinds of contributions. Please see the [CONTRIBUTING guidelines](./CONTRIBUTING.md) to get started.

### Special Mentions

There have already been incredible community contributors who are driving this project forward:

- [Jerron Lim (@StreetLamb)](https://github.com/StreetLamb) -- who has contributed countless hours and excellent examples, and great ideas to the project.
- [Jason Summer (@jasonsum)](https://github.com/jasonsum) -- for identifying several issues and adapting his Gmail MCP server to work with mcp-agent

## Roadmap

We will be adding a detailed roadmap (ideally driven by your feedback). The current set of priorities include:

- **Durable Execution** -- allow workflows to pause/resume and serialize state so they can be replayed or be paused indefinitely. We are working on integrating [Temporal](./src/mcp_agent/executor/temporal.py) for this purpose.
- **Memory** -- adding support for long-term memory
- **Streaming** -- Support streaming listeners for iterative progress
- **Additional MCP capabilities** -- Expand beyond tool calls to support:
  - Resources
  - Prompts
  - Notifications

## FAQs

### What are the core benefits of using mcp-agent?

mcp-agent provides a streamlined approach to building AI agents using capabilities exposed by **MCP** (Model Context Protocol) servers.

MCP is quite low-level, and this framework handles the mechanics of connecting to servers, working with LLMs, handling external signals (like human input) and supporting persistent state via durable execution. That lets you, the developer, focus on the core business logic of your AI application.

Core benefits:

- 🤝 **Interoperability**: ensures that any tool exposed by any number of MCP servers can seamlessly plug in to your agents.
- ⛓️ **Composability & Cutstomizability**: Implements well-defined workflows, but in a composable way that enables compound workflows, and allows full customization across model provider, logging, orchestrator, etc.
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

### Tell me a fun fact

I debated naming this project _silsila_ (سلسلہ), which means chain of events in Urdu. mcp-agent is more matter-of-fact, but there's still an easter egg in the project paying homage to silsila.
