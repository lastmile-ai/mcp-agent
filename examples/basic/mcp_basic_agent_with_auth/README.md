# Basic MCP Agent with authorization example 

The basic example is identical to `mcp_basic_agent` except that it adds an authorization configuration using a `BasicAgentDemoAuthEngine` derived class to intercept the Agent class's `list_tools` API. Please follow that `mcp_basic_agent` example's README for basic setup.

The authorization engine configuration is this stanza from `mcp_agent.config.yaml`

```yaml
authorization_engines:
  agents:
    finder:
      # api->engines map. "demo-auth" is registered in main.py
      api_engines: { list_tools: "demo-auth", attach_llm: "demo-auth" }
```

Different Agents (such as `finder` Agent in the example) can have different API engines hooked to various APIs. Different APIs within the same agent can specify different registered authorized engines as well. APIs not configured for authorization will be invoked directly.
