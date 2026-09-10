# HOL Guard tool approval

This example shows how to protect MCP tool execution with
[HOL Guard](https://github.com/hashgraph-online/hol-guard) without adding a new
mcp-agent core dependency or interception API.

`HolGuardedOpenAIAugmentedLLM` overrides `AugmentedLLM.pre_tool_call()` and sends
one JSON object to a locally configured Guard command before each MCP tool call:

```json
{
  "tool_call_id": "call_123",
  "tool_name": "fetch",
  "arguments": { "url": "https://modelcontextprotocol.io/" }
}
```

The tool runs only when Guard prints JSON containing either
`{"decision":"allow"}` or `{"allow":true}`. Deny, review, malformed output,
command failure, timeout, or an unavailable Guard binary all fail closed by
returning `False`, which prevents the downstream MCP tool from executing.

## Setup

```bash
cd examples/basic/hol_guard_tool_approval
uv pip install -r requirements.txt
cp mcp_agent.secrets.yaml.example mcp_agent.secrets.yaml
# Add OPENAI_API_KEY in the secrets file or environment.
```

Install HOL Guard separately and verify that its command is available before
running the example. If your installation uses a different executable name or
wrapper, point `HOL_GUARD_COMMAND` at that command.

```bash
hol-guard --help
```

Configure HOL Guard if the executable is not named `hol-guard`:

```bash
export HOL_GUARD_COMMAND="hol-guard"
export HOL_GUARD_TIMEOUT_SECONDS=10
```

Then run:

```bash
uv run main.py
```

## Files

- `hol_guard_llm.py` — the fail-closed `pre_tool_call` hook.
- `main.py` — minimal agent wiring using the existing `fetch` MCP server.
- `mcp_agent.config.yaml` — example server and OpenAI model configuration.
