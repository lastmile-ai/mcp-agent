# OAuth Examples

Two complementary scenarios demonstrate how OAuth integrates with MCP:

## interactive_tool

Shows the full authorization code flow for a synchronous tool. When the
client calls the tool, the server sends an `auth/request` message and the
client walks the user through the browser-based login. Subsequent tool calls
reuse the stored token—after the first run, re-run
`uv run examples/oauth/interactive_tool/client.py` (with the server still
running) and you should see the result immediately with no additional prompt.

## pre_authorize

Demonstrates seeding tokens via the `workflows-store-credentials` tool before running
an asynchronous workflow. This is useful when workflows execute in the
background (e.g., Temporal) and cannot perform interactive authentication on
their own.

## Using Redis for token storage

If you want to exercise the Redis-backed token store instead of the default
in-memory store:

1. Start a Redis server (for example: `docker run --rm -p 6379:6379 redis:7-alpine`).
2. Install the extra dependencies: `pip install -e .[redis]`.
3. Export `OAUTH_REDIS_URL`, e.g. `export OAUTH_REDIS_URL=redis://127.0.0.1:6379`.
4. Run the examples as usual (interactive tool or workflow). Tokens will be
   cached in Redis and server restarts will reuse them.
