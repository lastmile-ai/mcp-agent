# Context Isolation Demo

This example shows how per-request context scoping prevents logs and
notifications from bleeding between concurrent MCP clients.

## Setup

- Install the example dependencies from this folder:
  ```bash
  uv pip install -r examples/mcp_agent_server/context_isolation/requirements.txt
  ```
- Optional: adjust `mcp_agent.config.yaml` if you want to tweak logging transports or
  register additional MCP backends.

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

## Expected output

- Server console highlights two `SetLevelRequest` operations (one per client) followed
  by a pair of `CallToolRequest` entries. You should also see an `emit_log` workflow
  execution for each client with parameters matching the client payloads.

- Client A prints both `debug` and `info` log notifications (one per tool call) and
  the `demo/echo` notification containing its session id:

  ```text
  [A] log debug: ...
  [A] log info: Workflow emit_log started execution ...
  [A] tool result: ... "level": "debug"
  ```

- Client B only prints the `error` log notification—even after the second tool call—
  confirming that the per-session
  log level (`error`) filters out the info/debug output:

  ```text
  [B] log error: ...
  [B] tool result: ... "level": "error"
  ```

If Client B ever receives an `info` or `debug` log entry, the request-scoped logging
override is not working and should be investigated.
