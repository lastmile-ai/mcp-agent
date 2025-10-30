# Context Isolation Demo

This example shows how per-request context scoping prevents logs and
notifications from bleeding between concurrent MCP clients.

## Running the example

1. Start the SSE server in one terminal:

   ```bash
   uv run python examples/mcp_agent_server/context_isolation/server.py
   ```

   The server listens on `http://127.0.0.1:8000/sse` and exposes a single tool
   (`emit_log`) that logs messages using the request-scoped context.

2. In a second terminal, run the clients script. It launches two concurrent
   clients that connect to the server, set independent logging levels, and call
   the tool.

   ```bash
   uv run python examples/mcp_agent_server/context_isolation/clients.py
   ```

   Each client prints the logs and `demo/echo` notifications it receives. Client
   A (set to `debug`) sees all messages it emits, while client B (set to
   `error`) only receives error-level output. Notifications are tagged with the
   originating session so you can observe the strict separation between the two
   clients.
