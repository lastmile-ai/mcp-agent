# Public API (beta)
See /v1 endpoints for runs, SSE, cancel, and artifacts.
Auth: X-API-Key from STUDIO_API_KEYS, or Bearer JWT via JWT_HS256_SECRET / JWT_PUBLIC_KEY_PEM.

## Admin API (experimental)

Mount the administrative API router to expose runtime management endpoints:

```python
from starlette.applications import Starlette
from mcp_agent.api.routes import add_admin_api

app = Starlette()
add_admin_api(app)  # mounts under /v1/admin
```

### Agents

* `GET /v1/admin/agents` – List registered `AgentSpec` definitions.
* `POST /v1/admin/agents` – Create a new agent at runtime.
* `PATCH /v1/admin/agents/{id}` / `DELETE /v1/admin/agents/{id}` – Update or remove an agent.
* `GET /v1/admin/agents/download` / `POST /v1/admin/agents/upload` – Export or import agents YAML.

### Tool registry

* `GET /v1/admin/tools` – Inspect discovered tools, enable/disable status, and agent assignments.
* `PATCH /v1/admin/tools` – Toggle tool availability.
* `POST /v1/admin/tools/assign/{agent_id}` – Update agent-to-tool assignments.
* `POST /v1/admin/tools/reload` – Force a discovery refresh.

### Orchestrator and workflows

* `GET /v1/admin/orchestrators/{id}/state` – Inspect orchestrator state; `PATCH` updates live metadata.
* `GET/POST /v1/admin/orchestrators/{id}/plan` – Read or replace the active plan tree.
* `GET/POST /v1/admin/orchestrators/{id}/queue` – Inspect or replace queued work items.
* `GET /v1/admin/orchestrators/{id}/events` – Stream SSE updates for dashboards.
* `GET /v1/admin/workflows` – List stored workflow definitions; `POST` creates new workflows.
* `PATCH/DELETE /v1/admin/workflows/{id}` – Modify or remove workflows.
* `POST /v1/admin/workflows/{id}/steps` – Append a step to a workflow; `PATCH`/`DELETE` individual steps.

### Human input

* `GET /v1/admin/human_input/requests` – Query pending human input prompts.
* `GET /v1/admin/human_input/stream` – Subscribe to pending request SSE stream.
* `POST /v1/admin/human_input/respond` – Post a response to a queued human input request.
