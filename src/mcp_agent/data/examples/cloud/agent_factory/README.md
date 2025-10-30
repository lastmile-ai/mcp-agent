# Cloud Agent Factory (Temporal + Custom Workflow Tasks)

This example routes customer-facing questions to specialized agents, augments
responses with in-code knowledge-base snippets, and shows how to preload custom
`@workflow_task` modules via `workflow_task_modules`.

## What's included

- `main.py` – exposes an `@app.async_tool` (`route_customer_request`) that looks up
  knowledge-base context via a workflow task and then routes the enriched
  question through an LLMRouter.
- `custom_tasks.py` – defines `knowledge_base_lookup_task` using the
  `@workflow_task` decorator. The task provides deterministic answers drawn from
  an embedded support knowledge base.
- `agents.yaml` – two sample agents (`support_specialist`, `product_expert`) that
  the router can delegate to.
- `run_worker.py` – Temporal worker entry point.
- `mcp_agent.config.yaml` – configures Temporal, lists
  `workflow_task_modules: [custom_tasks]` so the worker imports the module before
  polling, and sets `workflow_task_retry_policies` to limit retries for the custom
  activity. Entries should be importable module paths (here `custom_tasks` lives
  alongside `main.py`, so we reference it by module name).

## Quick start

1. Install dependencies and add secrets:
   ```bash
   cd examples/cloud/agent_factory
   cp mcp_agent.secrets.yaml.example mcp_agent.secrets.yaml  # add OPENAI_API_KEY
   uv pip install -r requirements.txt
   ```

2. Start Temporal elsewhere:
   ```bash
   temporal server start-dev
   ```

3. Launch the worker:
   ```bash
   uv run run_worker.py
   ```

4. In another terminal, run the app:
   ```bash
   uv run main.py
   ```
   The tool will fetch knowledge-base context via the workflow task (executed as
   a Temporal activity) and produce a routed response.

5. Optional: connect an MCP client while `main.py` is running:
   ```bash
   npx @modelcontextprotocol/inspector --transport sse --server-url http://127.0.0.1:8000/sse
   ```

## How it works

1. `workflow_task_modules` ensures `custom_tasks.py` is imported during worker
   startup, registering `knowledge_base_lookup_task` with the app.
2. `route_customer_request` runs as a Temporal workflow (courtesy of
   `@app.async_tool`). Inside the workflow we call
   `context.executor.execute(knowledge_base_lookup_task, {...})`; this schedules
   the task as an activity, returning curated snippets.
3. The prompt is enriched with those snippets and routed through the factory
   helper (`create_router_llm`) to select the best agent and compose the final
   reply.

You can expand the example by adding more entries to the knowledge base or by
introducing additional workflow tasks. Simply place them in `custom_tasks.py`
and keep the module listed in `workflow_task_modules`.
