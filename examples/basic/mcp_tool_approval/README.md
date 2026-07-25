# Pre-tool Approval for MCP Calls

This example uses `AugmentedLLM.pre_tool_call` to apply an application-provided
decision function immediately before dispatch. Its filesystem policy uses exact
tool names and fails closed:

| Operation | Default decision |
| --- | --- |
| Allowlisted filesystem reads | Allow |
| Allowlisted filesystem changes | Require approval |
| Delete, shell, package, Git, and unknown tools | Block |
| Obvious sensitive paths | Block |

Decisions are appended to `logs/policy-audit.jsonl`. Audit records contain an
arguments digest rather than raw arguments. Replace the decision function,
approval callback, and JSONL sink with controls appropriate for your
application.

## Run

Install Python and `uv`, plus Node.js/npm with `npx` available on `PATH`.

```bash
cp mcp_agent.secrets.yaml.example mcp_agent.secrets.yaml
# Add your provider key to the ignored secrets file.
uv run main.py
```

The sensitive-path check is intentionally narrow and is not workspace
confinement or a complete path-security implementation. Use an MCP server rooted
at the intended workspace and Docker, a VM, a dev container, or another OS
isolation boundary when containment is required.

## Enforcement boundary

The `pre_tool_call` hook covers calls dispatched through this augmented LLM.
Direct calls to `Agent.call_tool`, another LLM instance, or a client connected
straight to the MCP server bypass this example.

Server-initiated MCP sampling (`sampling/createMessage`) is also a separate
protocol path and does not pass through `pre_tool_call`. Apply an equivalent
policy in the sampling callback or client session before enabling sampling.

## Tests

The focused tests use fake approval and audit components. They verify hook
return values, approval and rejection, exact-name fail-closed behavior,
sensitive paths, and redacted JSONL persistence without starting an MCP server
or calling an LLM.

```bash
uv run pytest tests/examples/test_mcp_tool_approval.py
```
