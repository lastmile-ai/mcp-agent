# MCP Agent example

```bash
uv run tracing/agent
```

This example shows tracing integration in a basic "finder" Agent which has access to the 'fetch' and 'filesystem' MCP servers.

The tracing implementation will log spans to the console for all agent methods.

### Exporting to Collector

If desired, [install Jaeger locally](https://www.jaegertracing.io/docs/2.5/getting-started/) and then update the `mcp_agent.config.yaml` to include a typed OTLP exporter with the collector endpoint (e.g. `http://localhost:4318/v1/traces`):

```yaml
otel:
  enabled: true
  exporters:
    - type: console
    - type: file
    - type: otlp
      endpoint: "http://localhost:4318/v1/traces"
```

<img width="2160" alt="Image" src="https://github.com/user-attachments/assets/93ffc4e5-f255-43a9-be3a-755994fec809" />
