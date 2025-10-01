# Tools Registry & Discovery

- Reads `tools/tools.yaml`
- Probes `/.well-known/mcp` or `/health`
- Caches results with TTL (`REGISTRY_REFRESH_SEC`)
- `GET /v1/tools` returns the live registry

Mount the API:
```python
from mcp_agent.api.routes.tools import add_tools_api
add_tools_api(app)
```
