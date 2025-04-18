# MCP Azure Agent Example - "Finder" Agent

This example demonstrates how to create and run a basic "Finder" Agent using Azure OpenAI model and MCP. The Agent has access to the `fetch` MCP server, enabling it to retrieve information from URLs.

## Setup

Check out the [Azure Python SDK docs](https://learn.microsoft.com/en-us/python/api/overview/azure/ai-inference-readme?view=azure-python-preview#getting-started) to obtain the following values:

- `endpoint`: E.g. `https://<your-resource-name>.services.ai.azure.com/models` or `https://<your-resource-name>.cognitiveservices.azure.com/openai/deployments/<your-deployment-name>`
- `api_key`

Example configurations:

```yaml
# mcp_agent.secrets.yaml

# Azure OpenAI inference endpoint
azure:
    default_model: gpt-4o-mini
    api_key: changethis
    endpoint: https://<your-resource-name>.cognitiveservices.azure.com/openai/deployments/<your-deployment-name>
    api_version: "2025-01-01-preview" # Azure OpenAI api-version. See https://aka.ms/azsdk/azure-ai-inference/azure-openai-api-versions

# Azure AI inference endpoint
azure:
    default_model: DeepSeek-V3
    api_key: changethis
    endpoint: https://<your-resource-name>.services.ai.azure.com/models
```

To return structured outputs for Azure OpenAI endpoints, you might need to include `api_version` as '2025-01-01-preview'.

Attach these values in `mcp_agent.secrets.yaml` or `mcp_agent.config.yaml`

## Running the Agent

To run the "Finder" agent, navigate to the example directory and execute:

```bash
cd examples/model_providers/mcp_basic_azure_agent

uv run --extra azure main.py
```
