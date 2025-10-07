# Tool Clients & Error Mapping

- Shared HTTP client (`mcp_agent.client.http.HTTPClient`) with timeouts, retries, and a simple circuit breaker.
- Canonical errors via `mcp_agent.errors.canonical.CanonicalError`.
- Typed adapters under `mcp_agent.adapters.*`, e.g., `GithubMCPAdapter`.

Env:
- `HTTP_TIMEOUT_MS` (default 3000)
- `RETRY_MAX` (default 2)
- `BREAKER_THRESH` (default 5)
- `BACKOFF_MS` (default 50)
- `BREAKER_COOLDOWN_MS` (default 30000)
