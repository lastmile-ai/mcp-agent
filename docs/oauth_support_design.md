# MCP Agent OAuth Support

## Goals
- Protect MCP Agent Cloud servers using OAuth 2.1 so MCP clients obtain tokens via standard flows.
- Enable MCP Agent runtimes to authenticate to downstream MCP servers that require OAuth access tokens.
- Provide pluggable token storage for both local development (in-memory) and multi-instance deployments (Redis planned).
- Maintain compatibility with MCP Authorization spec (RFC 8414, RFC 9728, OAuth 2.1 + PKCE, Resource Indicators) and the proposed delegated authorization SEP.

## Architecture Overview

### Components
1. **Auth Server Integration** – Configure the FastMCP instance with `AuthSettings` and a custom `TokenVerifier` that calls MCP Agent Cloud auth services.
2. **Protected Resource Metadata** – Serve `/.well-known/oauth-protected-resource` using FastMCP hooks so clients can discover the auth server.
3. **Access Token Validation** – Enforce bearer tokens on every inbound MCP request via `RequireAuthMiddleware`, populating the request context with the authenticated user.
4. **OAuth Token Service** – New `mcp_agent.oauth` package with:
  - `TokenStore`/`TokenRecord` abstractions
  - `InMemoryTokenStore` and Redis-backed implementation (optional for multi-instance)
   - `TokenManager` orchestration (acquire, refresh, revoke)
   - `OAuthHttpxAuth` for attaching tokens to downstream HTTP transports
   - `AuthorizationFlowCoordinator` that interacts with the user via MCP `auth/request`
5. **Delegated Authorization UI Flow** – Extend the gateway/session relay so servers can send `auth/request` messages to MCP clients, capturing authorization codes via either:
   - Client-returned callback URL (preferred, works with SEP-capable clients)
   - MCP Agent hosted callback endpoint (`/internal/oauth/callback/{flow_id}`) as a fallback / native-app style loopback.
6. **Configuration Surface** – Extend `Settings` and per-server `MCPServerAuthSettings` to describe OAuth behaviour (scopes, preferred auth server, redirect URIs, etc.) and global token-store configuration.

### Key Data Flow
1. **Inbound Requests**
   - Client presents bearer token ⇒ `BearerAuthBackend` + `MCPAgentTokenVerifier` introspect token.
   - Verified token populates context with `OAuthUserIdentity` (provider + subject + email).
   - Context is propagated into workflows/sessions so downstream OAuth flows know the acting user.

2. **Outbound HTTP (downstream MCP server)**
   - `ServerRegistry` detects `auth.oauth` configuration.
   - Wraps HTTP transport with `OAuthHttpxAuth` which requests an access token from `TokenManager`.
   - `TokenManager` checks store; if missing/expired ⇒ `AuthorizationFlowCoordinator` performs RFC 9728 discovery, PKCE, delegated browser flow through MCP client, exchanges code for tokens, caches result.
   - Requests automatically retry after token refresh when a response returns 401/invalid token.

3. **Token Storage**
   - Tokens stored per `(user_identity, resource, authorization_server)` tuple with metadata (scopes, expiry, refresh token, provider claims).
   - Store implements optimistic locking to avoid concurrent refresh storms.
   - Pluggable backend (`InMemoryTokenStore` initial, Redis follow-up).

## Module Plan

```
src/mcp_agent/oauth/
  __init__.py
  identity.py           # OAuthUserIdentity, helpers to extract from auth context
  records.py            # TokenRecord dataclass/pydantic model
  store/base.py         # TokenStore protocol
  store/in_memory.py    # Default store
  manager.py            # TokenManager (get/refresh/invalidate)
  flow.py               # AuthorizationFlowCoordinator
  http/auth.py          # OAuthHttpxAuth (httpx.Auth implementation)
  metadata.py           # RFC 8414 + RFC 9728 discovery helpers
  pkce.py               # PKCE + state utilities
  errors.py             # Custom exception hierarchy
```

Integration touchpoints:
- `mcp_agent/config.py` – add OAuth settings models.
- `mcp_agent/core/context.py` – add `token_manager`, `token_store`, `oauth_config` fields.
- `mcp_agent/app.py` – initialize token store/manager based on settings.
- `mcp_agent/server/app_server.py` – configure FastMCP auth settings, register callback route, surface user identity, extend relay to handle `auth/request`.
- `mcp_agent/mcp/mcp_server_registry.py` & `mcp_agent/mcp/mcp_connection_manager.py` – wire `OAuthHttpxAuth` into HTTP transports and expose helper for manual token teardown.
- `mcp_agent/mcp/client_proxy.py` – add proxy helpers for `auth/request`.
- `SessionProxy` – add direct request helper for `auth/request` and ensure Temporal flow support.
- `examples/mcp_agent_server/*` – demonstrate configuration changes.
- Tests – new suite exercising token store, metadata discovery, flow orchestration (with mocked HTTP + client responses).

## OAuth Flow Details
1. **Discovery**
   - If downstream server responds 401 with `WWW-Authenticate`, parse for `resource_metadata` ⇒ GET metadata ⇒ determine auth server URL(s).
   - Fetch authorization server metadata (RFC 8414).
   - Perform optional dynamic client registration when configured and supported.

2. **Authorization Request**
   - Generate PKCE challenge/verifier, secure `state`, choose `redirect_uri`.
   - Build authorization URL including `resource` parameter (RFC 8707) + requested scopes.
   - Invoke `auth/request` via SessionProxy → MCP client opens browser.

3. **Callback Handling**
   - Preferred: MCP client returns callback URL payload via request result.
   - Fallback: Authorization server redirects to `/internal/oauth/callback/{flow_id}`.
   - Coordinator validates `state`, extracts `code` (and errors).

4. **Token Exchange / Storage**
   - POST token endpoint with code + PKCE verifier + resource.
   - Store access token, refresh token, expiry, scope, provider metadata.
   - Associate tokens with user identity for reuse.

5. **Refresh / Revocation**
   - Manager refreshes when expiry within configurable grace window.
   - Invalidate token on refresh failure or when server responses indicate revocation.
   - Provide method to revoke tokens via authorization server when supported.

## Open Questions / Follow-ups
- Additional operational hardening (token rotation policies, rate limits).
- How LastMile auth server exposes token introspection + JWKS; need concrete endpoint specs to finalize `MCPAgentTokenVerifier`.
- MCP client adoption of `auth/request` SEP – need capability detection; until widely supported we rely on hosted callback fallback & manual instructions.
- Access control DSL (include/exclude by email/domain) – to be evaluated once token identity payload finalized.

## Testing Strategy
- Unit tests for token store concurrency + expiry handling.
- Metadata discovery + PKCE generation (pure python tests).
- Integration-style test for delegated flow using mocked HTTP server + fake MCP client (ensures `auth/request` plumbing works end-to-end).
- Tests around server 401 enforcement + WWW-Authenticate header.
