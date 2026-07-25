# MCP Tool Approval Gateway

This example uses the framework's `AugmentedLLM.pre_tool_call` hook to evaluate
MCP tool calls immediately before dispatch. The example policy is deliberately
small and fail-closed:

| Operation | Default decision |
| --- | --- |
| Allowlisted reads and read-only commands | Allow |
| Workspace writes and package installation | Require approval |
| Delete, push, unknown shell, and unknown tools | Block |
| Force-push, sensitive paths, and suspected exfiltration | Block as critical |

Decisions are appended to `logs/policy-audit.jsonl`. Audit records contain an
arguments digest rather than raw arguments. Replace the example rules, approval
callback, and JSONL sink with controls appropriate for your deployment.

## Run

```bash
cp mcp_agent.secrets.yaml.example mcp_agent.secrets.yaml
# Add your provider key to the ignored secrets file.
uv run main.py
```

The policy layer is an execution guard, not a sandbox. Use Docker, a VM, a dev
container, or another OS isolation boundary when containment is required.

## Enforcement boundary

The `pre_tool_call` hook covers calls dispatched through this augmented LLM.
Direct calls to `Agent.call_tool`, another LLM instance, or a client connected
straight to the MCP server bypass this example gateway.

Server-initiated MCP sampling (`sampling/createMessage`) is also a separate
protocol path and does not pass through `pre_tool_call`. Apply an equivalent
policy in the sampling callback or client session before enabling sampling.

## Tests

The focused tests use a fake approval callback and audit sink. They verify
allowlisted reads, approved writes, blocked execution, critical classification,
and redacted JSONL persistence without starting an MCP server or calling an LLM.

```bash
uv run pytest tests/examples/test_mcp_tool_approval.py
```
