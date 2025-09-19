# MCP Google Agent Example - "Finder" Agent

This example demonstrates how to create and run a basic "Finder" Agent using Google's Gemini models and MCP. The Agent has access to the `fetch` MCP server, enabling it to retrieve information from URLs.

## `1` App set up

First, clone the repo and navigate to the MCP Google Finder Agent example:

```bash
git clone https://github.com/lastmile-ai/mcp-agent.git
cd mcp-agent/examples/model_providers/mcp_basic_google_agent
```

Install `uv` (if you don’t have it):

```bash
pip install uv
```

Sync `mcp-agent` project dependencies:

```bash
uv sync
```

Install requirements specific to this example:

```bash
uv pip install -r requirements.txt
```

## `2` Set up secrets and environment variables

Before running the agent, ensure you have your Gemini Developer API or Vertex AI configuration details set up:

### Required Parameters

- `api_key`: Your Gemini Developer API key (can also be set via GOOGLE_API_KEY environment variable)

### Optional Parameters

- `vertexai`: Boolean flag to enable VertexAI integration (default: false)
- `project`: Google Cloud project ID (required if using VertexAI)
- `location`: Google Cloud location (required if using VertexAI)
- `default_model`: Defaults to "gemini-2.5-flash" but can be customized in your config

You can provide these in one of the following ways:

Configuration Options

1. Via `mcp_agent.secrets.yaml` or `mcp_agent.config.yaml`:

   ```yaml
   google:
     api_key: "your-google-api-key"
     vertexai: false
     # Include these if using VertexAI
     # project: "your-google-cloud-project"
     # location: "us-central1"
   ```

2. Via environment variables (e.g., GOOGLE_API_KEY)

## `3` Run locally

To run the "Finder" agent, navigate to the example directory and execute:

```bash
cd examples/model_providers/mcp_basic_google_agent

uv run main.py
```
