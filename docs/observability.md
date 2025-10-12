# Observability and Audit

This document summarises how the agent emits telemetry and where long lived
artifacts are persisted.  The goal is to make it simple to reason about a
single run end-to-end, from the spans emitted during execution to the audit
records stored on disk.

## Tracing

* A 32 character hexadecimal `trace_id` is generated for each run.  The helper
  utilities in `mcp_agent.telemetry.tracing` configure an OpenTelemetry tracer
  provider using the OTLP HTTP exporter when `OTEL_EXPORTER_OTLP_ENDPOINT` is
  set.
* Sampling is parent based with the ratio controlled by `OBS_SAMPLER_RATIO`
  (defaults to 0.1).  The ratio can be increased to `1.0` when troubleshooting.
* Stage spans follow the taxonomy `run.prepare`, `run.assemble`, `run.prompt`,
  `run.apply`, `run.test`, and `run.repair`.  Tool and model integrations are
  expected to add nested spans to capture latency and error metadata.

## Metrics

`mcp_agent.telemetry.metrics` defines counters and histograms for key service
level indicators including run durations, LLM latency, tool latency, and SSE
event counts.  The module initialises a `MeterProvider` that exports via OTLP
when an endpoint is configured, otherwise measurements are emitted to the
console which keeps unit tests hermetic.

### Environment variables

| Variable | Description | Default |
| --- | --- | --- |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | OTLP HTTP endpoint for both traces and metrics. | unset |
| `OBS_SAMPLER_RATIO` | Sampling ratio applied by the parent based sampler. | `0.1` |
| `OTEL_METRIC_EXPORT_INTERVAL` | Metric export interval in seconds. | `60` |

## Structured logging

`mcp_agent.logging.redact.RedactionFilter` installs on the primary logger to
scrub sensitive keys such as `Authorization` headers, `GITHUB_TOKEN`, and any
`*_API_KEY` values.  The filter rewrites both log messages and structured
payloads ensuring CI checks can assert the absence of secrets.

## Audit trail

Audit events are appended to `artifacts/<run_id>/audit.ndjson` via
`mcp_agent.audit.store.AuditStore`.  Each record is structured JSON containing
the timestamp, actor, action, target, params hash, outcome, and error code.  The
store enforces allowed actors (`system`, `studio`, `sentinel`) and writes files
with `0640` permissions.

Toggle audit logging by setting `AUDIT_ENABLED=false` in the environment.  When
disabled the store will refuse writes to avoid implying persistence where there
is none.

## Artifact layout

Artifacts are persisted under `artifacts/<run_id>/` using the following layout:

```
artifacts/<run_id>/
  run-summary.json
  context.manifest.json
  pack.hash
  junit.xml
  audit.ndjson
  diffs/
    <relative patches>
```

Each artifact has a companion metadata file ending in `.meta.json` which stores
its media type.  The `ArtifactIndex` service enumerates the directory and
produces a canonical index containing the filename, size, checksum, and media
type for every file.

## Cleanup and retention

Artifacts live under the directory specified by `ARTIFACTS_ROOT` (defaults to
`./artifacts`).  Deployments can configure background jobs that remove runs
older than `ARTIFACT_RETENTION_DAYS` while keeping the directory structure in
tact.  Audit files are append only and should not be rewritten outside the
retention window.

