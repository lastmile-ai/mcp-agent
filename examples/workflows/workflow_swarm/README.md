# MCP Swarm Agent

mcp-agent implements [OpenAI's Swarm pattern](https://github.com/openai/swarm) for multi-agent workflows, but in a way that can be used with any model provider.

**This example is taken from the [Swarm repo](https://github.com/openai/swarm/blob/main/examples/airline), and shown to work with MCP servers and Anthropic models (and can of course also work with OpenAI models).**

This example demonstrates a multi-agent setup for handling different customer service requests in an airline context using the Swarm framework. The agents can triage requests, handle flight modifications, cancellations, and lost baggage cases.

https://github.com/user-attachments/assets/b314d75d-7945-4de6-965b-7f21eb14a8bd

## Agents

1. **Triage Agent**: Determines the type of request and transfers to the appropriate agent.
2. **Flight Modification Agent**: Handles requests related to flight modifications, further triaging them into:
   - **Flight Cancel Agent**: Manages flight cancellation requests.
   - **Flight Change Agent**: Manages flight change requests.
3. **Lost Baggage Agent**: Handles lost baggage inquiries.
