# MCP Agent example

```bash
uv run tracing/llm
```

This example shows tracing integration for AugmentedLLMs.

The tracing implementation will log spans to the console for all AugmentedLLM methods.

### Exporting to Collector

If desired, [install Jaeger locally](https://www.jaegertracing.io/docs/2.5/getting-started/) and then update the `mcp_agent.config.yaml` for this example to have `otel.otlp_settings.endpoint` point to the collector endpoint (e.g. `http://localhost:4318/v1/traces` is the default for Jaeger via HTTP).

<img width="2160" alt="Image" src="https://github.com/user-attachments/assets/f2d1cedf-6729-4ce1-9530-ec9d5653103d" />
