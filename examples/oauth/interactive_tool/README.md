# OAuth Interactive Tool Example

This example shows the end-to-end OAuth **authorization code** flow for a
simple synchronous MCP tool. The MCP server exposes a `github_org_search`
tool that calls the GitHub MCP server. When the tool is invoked without a
cached token, the server issues an `auth/request` message and the client opens
the browser so you can complete the GitHub sign-in.

## Prerequisites

1. Create a GitHub OAuth App (Settings → Developer settings → OAuth Apps)
   and set the **Authorization callback URL** to `http://127.0.0.1:33418/callback`.
   (The example pins its loopback listener to that port, so the value must
   match exactly.)
   GitHub does not accept the RFC 8707 `resource` parameter, so the example
   disables it via `include_resource_parameter: false` in the server config.
2. Export the client credentials:

   ```bash
   export GITHUB_CLIENT_ID="your_client_id"
   export GITHUB_CLIENT_SECRET="your_client_secret"
   ```

3. Install dependencies (from the repository root):

   ```bash
   pip install -e .
   ```

## Running

Start the MCP server in one terminal:

```bash
python examples/oauth/interactive_tool/server.py
```

In another terminal, run the client:

```bash
python examples/oauth/interactive_tool/client.py
```

The client will display an authorization prompt. Approve it in the browser
and GitHub will redirect back to the local callback handler. Once completed,
the tool result is printed in the client terminal.

The server and client use stable session IDs so the OAuth token is cached and
reused across runs. Once the first authorization completes, subsequent
invocations should return immediately without reopening the browser.

## Optional: Redis-backed token store

By default the example keeps tokens in memory. To persist tokens across server
restarts, switch to the Redis token store:

1. Install the Redis extra:

   ```bash
   pip install -e .[redis]
   ```

2. Start a Redis instance (for example, Docker):

   ```bash
   docker run --rm -p 6379:6379 redis:7-alpine
   ```

3. Export `OAUTH_REDIS_URL` before launching the server:

   ```bash
   export OAUTH_REDIS_URL="redis://127.0.0.1:6379"
   ```

With the environment variable set, the server automatically switches to Redis
(`mcp_agent:oauth_tokens` prefix by default) and will reuse tokens even after
restarts.
