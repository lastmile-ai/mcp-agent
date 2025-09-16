# Deploying the elicitation example to the cloud

In `mcp_agent.secrets.yaml`, set your OpenAI `api_key`.

Then, in the current directory (`cloud`), run:

```bash
uv run mcp-agent deploy elicitation --config-dir .
```

Once deployed, you should see an app ID, and a URL in the output. 
You can use the URL to access the MCP via e.g. the [MCP Inspector](https://github.com/modelcontextprotocol/inspector).
Add `/sse` to the end of the url, as the MCP is exposed as a server-sent events endpoint.
Do not forget to add an authorization header with your MCP-agent API key as the bearer token.

The app ID can be used to delete the example again afterward:

```bash
uv run mcp-agent cloud app delete --id=<app-id>
```