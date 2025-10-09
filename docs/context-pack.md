# ContextPack Assembly

## CLI

Assemble a ContextPack from an inputs JSON:

```bash
python scripts/context_assemble.py assemble --inputs assets/examples/context.inputs.tiny.json --out manifest.json --dry-run
```

Flags:
- `--top-k`, `--neighbor-radius`
- `--token-budget`, `--max-files`
- Per-tool timeouts: `--semantic-timeout-ms`, `--symbols-timeout-ms`, `--neighbors-timeout-ms`, `--patterns-timeout-ms`

Output:
- Prints `pack_hash` and a budget summary to stdout
- Writes `manifest.json` when `--out` is provided

## Enforcement

Set `MCP_CONTEXT_ENFORCE_NON_DROPPABLE=true` to make the CLI exit non-zero when any `must_include` span is not fully covered by the resulting slices.
