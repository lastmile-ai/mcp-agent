# Tools Registry & Discovery

The tools registry exposes a cached, deterministic catalog of MCP servers via
`GET /v1/tools`. The endpoint powers Studio and the orchestrator, providing a
stable list of available tools alongside health, versioning, and capability
metadata.

## Configuration

| Environment Variable | Default | Description |
| -------------------- | ------- | ----------- |
| `TOOLS_YAML_PATH` | `tools/tools.yaml` | Static inventory file that lists MCP servers. |
| `REGISTRY_REFRESH_SEC` | `60` | Base refresh cadence for discovery probes. |
| `REGISTRY_STALE_MAX_SEC` | `3600` | Retain the last successful snapshot for this long when probes fail. |
| `DISCOVERY_TIMEOUT_MS` | `1500` | HTTP timeout for `.well-known/mcp` and `/health` checks. |
| `DISCOVERY_UA` | `agent-mcp/PR-06` | User-Agent sent with discovery requests. |
| `TOOLS_REGISTRY_ENABLED` | `true` | Feature flag for the background refresh task. |
| `REGISTRY_ALLOWED_HOSTS` | _unset_ | Optional CSV allow-list for discovery targets. |

Inventory entries are simple YAML objects:

```yaml
- id: github-mcp
  name: GitHub MCP
  base_url: https://github-mcp.internal:8080
  headers:
    Authorization: Bearer ${GITHUB_TOKEN}
  tags: [scm, internal]
```

## Discovery Pipeline

1. Load static inventory from `TOOLS_YAML_PATH`.
2. Probe `/.well-known/mcp` for metadata (`name`, `version`, `capabilities`).
3. Probe `/health` to determine `alive` status.
4. Normalize results with deterministic ordering, TTL/jitter scheduling, and
   exponential backoff on failure.
5. Publish metrics (`tools_discovery_latency_ms`, `tools_registry_size`, etc.)
   and structured logs with `phase` hints.

The registry keeps the last good capabilities for up to
`REGISTRY_STALE_MAX_SEC` when probes fail, ensuring cached responses remain
useful during transient outages.

## API Usage

Mount the router inside your Starlette application:

```python
from mcp_agent.api.routes.tools import add_tools_api

add_tools_api(app)
```

Request `GET /v1/tools` to retrieve the snapshot. Query parameters allow
filtering by `alive`, `capability`, `tag`, or substring `q` against the tool
name/id. Responses include deterministic `registry_hash` values (also surfaced
as a weak `ETag`) suitable for caching and change detection.

