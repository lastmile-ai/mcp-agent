# Implementation Plan

## 1. Workflow-level retry controls (stop runaway executions)

### Goal
Provide a way to cap retries for an entire workflow run (not just individual activities) so Temporal executions stop after a configurable number of failures.

### Key changes
- **Configuration:**
  - Extend `TemporalSettings` (and generated schema/docs) with an optional `workflow_retry_policy: WorkflowTaskRetryPolicy | None`.
  - Allow per-workflow overrides via `@app.workflow(..., retry_policy=...)` or a `workflow_retry_policy` attribute on the workflow class so multi-tenant apps can mix defaults and overrides.
- **Workflow metadata plumbing:**
  - Teach `MCPApp.workflow()` / `Workflow` base class to record the resolved retry policy (config default + decorator override) in metadata accessible when starting the workflow.
  - Update `Workflow.run_async` so it passes the policy to the executor when delegating to Temporal.
- **Temporal executor:**
  - Update `TemporalExecutor.start_workflow()` to accept a `RetryPolicy | dict | None` argument and forward it to `TemporalClient.start_workflow(..., retry_policy=...)`.
  - Convert `WorkflowTaskRetryPolicy` to Temporal kwargs when building the policy object.
- **Docs & UX:**
  - Document the new settings in `docs/advanced/temporal.mdx` and configuration reference so operators know how to stop infinite retries.
  - Mention interaction with per-activity policies (workflow retry caps the outer loop; activities still control their own backoff).

### Step-by-step
1. **Schema & settings**
   - Add `workflow_retry_policy` to `TemporalSettings` (`src/mcp_agent/config.py`) and update `schema/mcp-agent.config.schema.json` + docs.
2. **Workflow decorator override**
   - Extend `MCPApp.workflow()` to accept `retry_policy: WorkflowTaskRetryPolicy | dict | None` and stash it on the class (e.g., `cls._workflow_retry_policy`).
3. **Propagate through Workflow.run_async**
   - When `execution_engine == "temporal"`, read the resolved policy (decorator override > config default) and pass it to `TemporalExecutor.start_workflow`.
4. **Temporal executor support**
   - Update `TemporalExecutor.start_workflow()` signature to accept `workflow_retry_policy`.
   - Build a `temporalio.common.RetryPolicy` instance if provided and supply it to `client.start_workflow`.
5. **Tests**
   - Add unit/integration tests that start a workflow designed to fail and assert Temporal only retries the configured number of times (mock `TemporalClient` in unit tests; optionally add an asyncio-engine fallback test verifying the decorator wiring doesn’t break non-Temporal runs).
6. **Docs**
   - Update Temporal guide + configuration reference with examples for both global and per-workflow configurations.

### Validation
- `pytest` for new tests around retry behavior.
- Manual sanity check: run a sample Temporal workflow with a forced failure and observe that it stops after `maximum_attempts`.
- Schema/doc build if enforced (make sure config schema CI passes).

## 2. Non-blocking execution for local (non-MCP) tools

### Goal
Ensure function-based tools (local Python callables added via `Agent.functions` or Swarm agents) execute via Temporal activities so slow operations (CLI utilities, network calls) don’t block workflow threads.

### Key changes
- **Execution strategy:**
  - When an agent initializes inside an MCPApp, auto-register each function tool as a Temporal activity (no global registries) and reuse the fast local path for asyncio.
  - Update `Agent.call_tool` and `Swarm.call_tool` to invoke the generated activity via the executor whenever `execution_engine == "temporal"`.
- **Developer ergonomics:**
  - Hide the registration mechanics from users—passing callables to `Agent(functions=[...])` continues to work, but documentation should note that functions must be module-level so workers can import them.
- **Concurrency controls:**
  - Respect existing `TemporalExecutor.config.max_concurrent_activities` so function tools obey user limits.

### Step-by-step
1. **Automatic activity registration**
   - During agent initialization (when an app context exists), wrap each function tool with `@app.workflow_task` and remember the generated activity callable.
2. **Agent.call_tool changes**
   - When `execution_engine == "temporal"`, invoke the cached activity through the executor instead of running the function inline; otherwise keep the fast local path.
3. **Swarm override**
   - Mirror the same behavior in `Swarm.call_tool` (delegating back to `Agent.call_tool`).
4. **Tests**
   - Add unit tests that:
     - Verify activities are registered during initialization and invoked when Temporal is in use.
     - Confirm asyncio execution still bypasses the executor.
5. **Docs**
   - Update the Temporal guide (and GitHub discussion #520 link) with guidance on defining module-scope functions, plus an example showing a long-running CLI tool executed safely via activities.

### Validation
- Unit tests for the new activity path.
- Integration/smoke example (e.g., run a sample workflow calling a mocked slow tool and confirm Temporal doesn’t deadlock).
- Documentation review to ensure users know how to opt in.

## 3. Structured LLM/tool telemetry (observable payloads)

### Goal
Emit a provider-agnostic, structured event/log schema that consistently captures LLM/tool inputs and outputs (plus metadata) so downstream systems and OTEL exporters can consume them without string matching.

### Key changes
- **Schema definition:** define a single JSON-friendly schema (fields like `event_type`, `agent`, `run_id`, `step_id`, `payload`, `redacted`, `error`, timestamps).
- **Base-class hooks:** update `AugmentedLLM` to emit these events at `_log_chat_progress`, `_log_chat_finished`, `call_tool` pre/post, and similar hook points. Provider subclasses should only supply normalized payloads; the base handles logging and OTEL emission.
- **Telemetry integration:** extend `mcp_agent/tracing/telemetry.py` with helpers to add OTEL span events mirroring the structured logs (respecting payload redaction options).
- **Redaction & config:** add settings to control whether prompts/responses/tool args are logged, with optional redaction callbacks.
- **Provider cleanup:** refactor provider-specific modules (OpenAI, Anthropic, etc.) to stop emitting ad-hoc logs and instead feed the centralized logger.

### Step-by-step
1. Finalize schema + helper utilities (e.g., `log_llm_event(event_type, payload, *, include_payloads=True)`).
2. Implement logging in `AugmentedLLM` base class for pre/post LLM calls and tool invocations.
3. Add configurable redaction toggles in settings (per agent or global).
4. Update provider subclasses to pass structured payloads to the base hooks (remove bespoke logging).
5. Ensure tools triggered outside AugmentedLLM (e.g., aggregator) also emit `tool_request/tool_response` events.
6. Write OTEL exporter helper to attach the same data as span events.

### Validation
- Unit tests verifying schema shape and redaction controls.
- Manual OTEL inspection to confirm events appear with consistent attribute names.
- Documentation snippet describing event schema and config knobs.

## 4. Execution trace reconstruction

### Goal
Provide a first-class way to capture and retrieve ordered execution traces (LLM/tool steps) for a workflow run so frontends can display them without scraping logs.

### Key changes
- **Trace store:** implement a lightweight collector (`mcp_agent.tracing.trace_store.TraceStore`) plus a contextvar helper so each workflow run can capture events under its `run_id`.
- **Workflow/agent API:** have `Workflow` register runs with the store (and expose `get_trace()`), while `AugmentedLLM`/tool emitters append events automatically via the shared context.
- **Export path:** optionally emit traces via OTEL span links or write to trace files when configured.

### Step-by-step
1. Build the in-memory (pluggable) trace store; ensure it handles concurrent runs.
2. Wire structured telemetry events into the trace store.
3. Add APIs on `Workflow`/`Context` to fetch or stream traces.
4. Provide serializer(s) (JSON list, NDJSON) for external consumers.
5. Document usage and lifecycle (retention, memory implications).

### Validation
- Unit tests verifying traces contain ordered steps and survive concurrent emissions.
- Example showing UI/CLI reconstruction from the stored trace.

## 5. Sub-agent planner example + documentation refresh

### Goal
Publish an end-to-end example that demonstrates the “planner spawns per-step sub-agents using non-blocking tools” pattern, incorporating the new telemetry/trace improvements.

### Key changes
- **Example workflow:** add a Temporal-based sample (`examples/temporal/planner_subagents_nonblocking.py`) that:
  - Uses the planner pattern to generate steps.
  - Dynamically creates sub-agents per step.
  - Invokes a slow external tool via the new activity path.
  - Emits structured telemetry/trace data.
- **Docs:** update planner/Temporal guides referencing the example and explaining how to expose traces to end users.
- **GitHub discussion:** respond to discussion #520 linking to the new example/pattern.

### Step-by-step
1. Implement the example workflow (config, workers, README).
2. Ensure it depends on features from items 1–4 (retry config, non-blocking tools, telemetry, trace store).
3. Update docs (planner pattern, Temporal guide, observability section) with snippets and instructions.
4. Provide quickstart commands for users to run the example locally.

### Validation
- Run the example end-to-end under Temporal, verifying planner, sub-agent creation, and tooling paths.
- Ensure documentation build/tests (if any) cover the new sections.
- Close the referenced GitHub discussion with a summary of the solution.
