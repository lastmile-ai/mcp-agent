# MCP Agent example

This example shows tracing integration in a basic "finder" Agent which has access to the 'fetch' and 'filesystem' MCP servers.

You can ask it information about local files or URLs, and it will make the determination on what to use at what time to satisfy the request.

The tracing implementation will log spans to the console.

### Exporting to Collector

If desired, [install Jaeger locally](https://www.jaegertracing.io/docs/2.5/getting-started/) and then update the `mcp_agent.config.yaml` for this example to have `otel.otlp_endpoint` point to the collector endpoint (e.g. `http://localhost:4318/v1/traces` is the default for Jaeger via HTTP).

<img width="2160" alt="Image" src="https://github.com/user-attachments/assets/TODO" />
