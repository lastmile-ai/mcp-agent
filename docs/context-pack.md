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

With `enforce_non_droppable=True`, the assembler raises a `BudgetError` as soon as a token, file, or section budget is exceeded. The exception captures the overflow metadata so orchestration layers can halt deterministically and surface a "stopping on limits" status to clients. When limits are soft, the resulting manifest metadata will include `"violation": true` and streaming emitters set a `violation` flag to notify UIs.

Every prune path records a `budget_overflow_count` metric labelled with the reason (e.g. `token_budget`, `max_files`, `resp_truncated`). These counters appear in OTEL dashboards and allow operators to audit overflow rates alongside assembly duration histograms.
