# MCP Agent example

```bash
uv run tracing/llm
```

This example shows tracing integration for AugmentedLLMs.

The tracing implementation will log spans to the console for all AugmentedLLM methods.

### Exporting to Collector

If desired, [install Jaeger locally](https://www.jaegertracing.io/docs/2.5/getting-started/):

```
docker run
 --rm --name jaeger \
  -p 16686:16686 \
  -p 4317:4317 \
  -p 4318:4318 \
  -p 5778:5778 \
  -p 9411:9411 \
  jaegertracing/jaeger:2.5.0
```

Then update the `mcp_agent.config.yaml` to include a typed OTLP exporter with the collector endpoint (e.g. `http://localhost:4318/v1/traces`):

```yaml
otel:
  enabled: true
  exporters:
    - type: console
    - type: file
    - type: otlp
      endpoint: "http://localhost:4318/v1/traces"
```

<img width="2160" alt="Image" src="https://github.com/user-attachments/assets/f2d1cedf-6729-4ce1-9530-ec9d5653103d" />
