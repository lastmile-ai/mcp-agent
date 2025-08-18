# Temporal Tracing Example

This example demonstrates how to use [Temporal](https://temporal.io/) as the execution engine for MCP Agent workflows, with OpenTelemetry tracing enabled.

## Prerequisites

- Python 3.10+
- [UV](https://github.com/astral-sh/uv) package manager
- A running Temporal server (see setup instructions below)
- Local [Jaeger installation](https://www.jaegertracing.io/docs/2.5/getting-started/)

## Setting Up Temporal Server

Before running these examples, you need to have a Temporal server running. The easiest way to get started is using the Temporal CLI:

1. Install the Temporal CLI by following the instructions at: https://docs.temporal.io/cli/

2. Start a local Temporal server:
   ```bash
   temporal server start-dev
   ```

This will start a Temporal server on `localhost:7233` (the default address configured in `mcp_agent.config.yaml`).

You can also use the Temporal Web UI to monitor your workflows by visiting `http://localhost:8233` in your browser.

## Configuration

The examples use the configuration in `mcp_agent.config.yaml`, which includes:

- Temporal server address: `localhost:7233`
- Namespace: `default`
- Task queue: `mcp-agent`
- Maximum concurrent activities: 10

## Running the Examples

To run any of these examples, you'll need to:

1. Install the required dependencies:

   ```bash
   uv pip install -r requirements.txt
   ```

2. Start the Temporal server (as described above)

3. Configure Jaeger Collector

[Run Jaeger locally](https://www.jaegertracing.io/docs/2.5/getting-started/) and then ensure the `mcp_agent.config.yaml` for this example has `otel.otlp_settings.endpoint` point to the collector endpoint (e.g. `http://localhost:4318/v1/traces` is the default for Jaeger via HTTP).

4. In a separate terminal, start the worker:

   ```bash
   uv run run_worker.py
   ```

   The worker will register all workflows with Temporal and wait for tasks to execute.

5. In another terminal, run the example workflow scripts:
   ```bash
   uv run basic.py
   ```
