# Run Lifecycle State Machine

The MCP agent exposes a deterministic state machine for every public run.  Each
transition is auditable, emits a real-time SSE notification, and records
telemetry for dashboards or automated monitoring.

## States

Runs may only occupy one of the following states:

| State | Description |
| --- | --- |
| `queued` | Run has been accepted and is waiting to start work. |
| `preparing` | The controller is loading configuration, repositories, or feature packs. |
| `assembling` | Artifacts (plans, prompts, caps) are being assembled before model use. |
| `prompting` | An LLM prompt is being executed.  LLM budget metrics are recorded here. |
| `applying` | Generated code or artifacts are being applied to the workspace. |
| `testing` | Automated checks are executing to validate the work. |
| `repairing` | The controller is repairing a failed test or applying a patch retry. |
| `green` | Run completed successfully. |
| `failed` | Run terminated with an unrecoverable error. |
| `canceled` | Run was canceled via API or internal signal. |

The legal transitions are encoded directly in
`mcp_agent.runloop.lifecyclestate.RunLifecycle`.  Any illegal transition raises
an exception and is reported as a `failed` terminal state.

```
queued → preparing → assembling → prompting → applying → testing
          ↘ cancel ↗             ↘ repair ↗       ↘ cancel ↗
```

Repairs loop between `repairing` and `applying`/`testing`.  Terminal states are
`green`, `failed`, and `canceled`.

## SSE Event Stream

Every transition results in an SSE message broadcast to all connected clients.
Messages follow the schema below and include a monotonically increasing
`event_id` that supports HTTP `Last-Event-ID` reconnection.

```json
{
  "run_id": "...",
  "state": "applying",
  "timestamp": "2024-05-30T20:15:22.512Z",
  "details": {
    "iteration": 2,
    "budget": {"llm_active_ms": 42, "remaining_s": 17.5}
  }
}
```

Terminal events close the stream while preserving the history so that new
clients can reconnect and replay the full state sequence.

## Cancel Semantics

`POST /v1/runs/{run_id}/cancel` sets a cancellation token, propagates the signal
into the controller, waits for the background task to terminate, and emits a
`canceled` state transition.  The controller ensures that any active LLM/tool
work is aborted and that no additional state transitions occur after cancel.

## Telemetry

Every transition increments the `run_state_transitions_total` counter and the
duration spent in the previous state is recorded in the
`run_state_duration_seconds` histogram.  Attributes include `run_id`,
`from`/`to` states, and `state` for duration measurements.  These metrics feed
observability dashboards showing trends such as average testing duration,
cancellation rates, or the most common failure stage.

## API Contract Summary

* `POST /v1/runs` returns a `queued` run immediately and begins processing in
  the background.
* `GET /v1/stream/{id}` streams lifecycle events in order, supports multiple
  concurrent clients, and honours the `Last-Event-ID` header for replay.
* `POST /v1/runs/{id}/cancel` emits `canceled` if the run is still in progress
  and is idempotent for terminal runs.

See `schema/public.openapi.json` for the full OpenAPI contract.
