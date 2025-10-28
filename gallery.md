# Example Gallery

This gallery collects runnable projects from `/examples` that correspond to sections in `README.md`. Each entry lists what it demonstrates, how to run it, and the most relevant documentation on https://docs.mcp-agent.com. Demo videos and community projects are grouped under **Spotlight demos** at the end.

## Basic agents

- **Finder agent** (`examples/basic/mcp_basic_agent/`) — multi-tool hello world that powers the Quickstart. Run `uv run main.py`. Docs: [Quickstart](https://docs.mcp-agent.com/get-started/quickstart).
- **Hello world** (`examples/basic/mcp_hello_world/`) — minimal agent with inline configuration and scripted tool wiring. Run `uv run main.py`. Docs: [Welcome](https://docs.mcp-agent.com/get-started/welcome).
- **Agent factory** (`examples/basic/agent_factory/`) — load `AgentSpec` definitions from YAML and compose routers programmatically. Run `uv run main.py`. Docs: [Agents](https://docs.mcp-agent.com/mcp-agent-sdk/core-components/agents).
- **Server aggregator** (`examples/basic/mcp_server_aggregator/`) — attach multiple MCP servers through the aggregator helper. Run `uv run main.py`. Docs: [MCP integration overview](https://docs.mcp-agent.com/mcp/overview).
- **Token counter** (`examples/basic/token_counter/`) — demonstrates token accounting, streaming updates, and usage summaries. Run `uv run main.py`. Docs: [Observability](https://docs.mcp-agent.com/mcp-agent-sdk/advanced/observability).
- **OAuth basic agent** (`examples/basic/oauth_basic_agent/`) — GitHub OAuth flow with token storage and delegated credentials. Run `uv run main.py`. Docs: [Authentication](https://docs.mcp-agent.com/mcp-agent-sdk/advanced/authentication).

## Workflow patterns

- **Parallel LLM** (`examples/workflows/workflow_parallel/`) — fan-out/fan-in specialists for map-reduce style plans. Run `uv run main.py`. Docs: [Parallel pattern](https://docs.mcp-agent.com/mcp-agent-sdk/effective-patterns/map-reduce).
- **Router** (`examples/workflows/workflow_router/`) — route requests across agents, MCP servers, and Python callables. Run `uv run main.py`. Docs: [Router pattern](https://docs.mcp-agent.com/mcp-agent-sdk/effective-patterns/router).
- **Intent classifier** (`examples/workflows/workflow_intent_classifier/`) — bucket requests into intents via embeddings or LLMs. Run `uv run main.py`. Docs: [Intent classifier](https://docs.mcp-agent.com/mcp-agent-sdk/effective-patterns/intent-classifier).
- **Evaluator–optimizer** (`examples/workflows/workflow_evaluator_optimizer/`) — iterate until a reviewer approves the output. Run `uv run main.py`. Docs: [Evaluator–optimizer](https://docs.mcp-agent.com/mcp-agent-sdk/effective-patterns/evaluator-optimizer).
- **Orchestrator** (`examples/workflows/workflow_orchestrator/`) — planner + worker coordination with task decomposition. Run `uv run main.py`. Docs: [Planner/orchestrator](https://docs.mcp-agent.com/mcp-agent-sdk/effective-patterns/planner).
- **Deep research** (`examples/workflows/workflow_deep_orchestrator/`) — long-horizon research with policy guardrails and knowledge extraction. Run `uv run main.py`. Docs: [Deep research](https://docs.mcp-agent.com/mcp-agent-sdk/effective-patterns/deep-research).
- **Swarm** (`examples/workflows/workflow_swarm/`) — demonstrates handoffs, human input, and signals compatible with OpenAI Swarm. Run `uv run main.py`. Docs: [Swarm pattern](https://docs.mcp-agent.com/mcp-agent-sdk/effective-patterns/swarm).

## Durable execution & Temporal

- **Temporal starter** (`examples/temporal/`) — run workflows on Temporal with a shared worker. Follow the `README.md`, run `uv run run_worker.py` in one terminal and `uv run main.py` in another. Docs: [Durable agents](https://docs.mcp-agent.com/mcp-agent-sdk/advanced/durable-agents) and [Temporal backend](https://docs.mcp-agent.com/advanced/temporal).
- **Human input over Temporal** (`examples/human_input/temporal/`) — pause workflows with `request_human_input` and resume via CLI payloads. Docs: [Signals & human input](https://docs.mcp-agent.com/mcp-agent-sdk/core-components/agents#human-input).

## Agent servers

- **Asyncio agent server** (`examples/mcp_agent_server/asyncio/`) — expose tools as an MCP server using stdio and built-in management tools. Run `uv run main.py`. Docs: [Agent servers](https://docs.mcp-agent.com/mcp-agent-sdk/mcp/agent-as-mcp-server).
- **Temporal agent server** (`examples/mcp_agent_server/temporal/`) — durable agent server with a Temporal worker and SSE endpoint. Run `uv run run_worker.py` then `uv run main.py`. Docs: [Agent servers + Temporal](https://docs.mcp-agent.com/mcp-agent-sdk/mcp/agent-as-mcp-server#temporal-variant).

## Cloud & deployment

- **Cloud async agent** (`examples/cloud/mcp/`) — structure of a deployable MCP server project. Run `uvx mcp-agent deploy`. Docs: [Cloud overview](https://docs.mcp-agent.com/cloud/overview) and [Deployment quickstart](https://docs.mcp-agent.com/cloud/deployment-quickstart).
- **Cloud Temporal agent** (`examples/cloud/temporal/`) — template for durable workloads with background workers and Temporal. Docs: [Cloud: durable workflows](https://docs.mcp-agent.com/cloud/use-cases/deploy-agents).

## Observability & controls

- **Tracing + token usage** (`examples/tracing/`) — export spans, stream structured logs, and summarise token usage. Run `uv run main.py`. Docs: [Observability](https://docs.mcp-agent.com/mcp-agent-sdk/advanced/observability).
- **Tool filters** (`examples/basic/mcp_tool_filter/`) — guard which tools are exposed to the LLM via decorators. Run `uv run main.py`. Docs: [Workflows & decorators](https://docs.mcp-agent.com/mcp-agent-sdk/core-components/workflows#tool-filter).

## MCP integration

- **MCP clients** (`examples/mcp/`) — call external MCP servers, aggregate results, and reuse `gen_client`. Run `uv run main.py`. Docs: [MCP integration overview](https://docs.mcp-agent.com/mcp/overview).
- **Model selector** (`examples/basic/mcp_model_selector/`) — customise provider/model choice dynamically. Run `uv run main.py`. Docs: [Augmented LLMs](https://docs.mcp-agent.com/concepts/augmented-llms#model-selection).

## Spotlight demos

- **Claude Desktop multi-agent evaluation** — Claude Desktop connected to the `mcp_agent_server` orchestration workflow. Code: [`examples/basic/mcp_server_aggregator`](./examples/basic/mcp_server_aggregator/). Thanks to [Jerron Lim (@StreetLamb)](https://github.com/StreetLamb).

  https://github.com/user-attachments/assets/7807cffd-dba7-4f0c-9c70-9482fd7e0699

- **Gmail Streamlit agent** — Drives Gmail actions (read/send/delete) via an MCP server from a Streamlit UI. Code: [gmail-mcp-server](https://github.com/jasonsum/gmail-mcp-server/blob/add-mcp-agent-streamlit/streamlit_app.py). Thanks to [Jason Summer (@jasonsum)](https://github.com/jasonsum).

  https://github.com/user-attachments/assets/54899cac-de24-4102-bd7e-4b2022c956e3

- **Streamlit RAG chatbot** — Answers questions against a Qdrant corpus with MCP servers. Code: [`examples/usecases/streamlit_mcp_rag_agent`](./examples/usecases/streamlit_mcp_rag_agent/). Thanks to [Jerron Lim (@StreetLamb)](https://github.com/StreetLamb).

  https://github.com/user-attachments/assets/f4dcd227-cae9-4a59-aa9e-0eceeb4acaf4

- **Marimo file finder** — Screenshot of the Quickstart finder agent running inside [Marimo](https://github.com/marimo-team/marimo). Code: [`examples/usecases/marimo_mcp_basic_agent`](./examples/usecases/marimo_mcp_basic_agent/). Thanks to [Akshay Agrawal (@akshayka)](https://github.com/akshayka).

  https://github.com/user-attachments/assets/139a95a5-e3ac-4ea7-9c8f-bad6577e8597

- **Swarm airline workflow** — Customer service workflow built with the Swarm pattern. Code: [`examples/workflows/workflow_swarm`](./examples/workflows/workflow_swarm/).

  https://github.com/user-attachments/assets/b314d75d-7945-4de6-965b-7f21eb14a8bd

---

Run every example with `uv run ...` (after `uv sync` or `uv install`). Secret files have `.example` variants—copy them to `mcp_agent.secrets.yaml` and fill in provider credentials before executing.
