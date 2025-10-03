# MCP Bedrock Agent Example - "Finder" Agent

This example demonstrates how to create and run a basic "Finder" Agent using AWS Bedrock and MCP. The Agent has access to the `fetch` MCP server, enabling it to retrieve information from URLs.

## `1` App set up

First, clone the repo and navigate to the MCP Bedrock Finder Agent example:

```bash
git clone https://github.com/lastmile-ai/mcp-agent.git
cd mcp-agent/examples/model_providers/mcp_basic_bedrock_agent
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

Before running the agent, ensure you have your AWS credentials and configuration details set up:

Parameters

- `aws_region`
- `aws_access_key_id`
- `aws_secret_access_key`
- `aws_session_token`

You can provide these in one of the following ways:

Configuration Options

1. Via `mcp_agent.secrets.yaml` or `mcp_agent.config.yaml`

```yaml
bedrock:
  default_model: anthropic.claude-3-haiku-20240307-v1:0
  aws_region:
  aws_access_key_id:
  aws_secret_access_key:
  aws_session_token:
```

2. Via your AWS config file (`~/.aws/config` and/or `~/.aws/credentials`)

Optional:

- `default_model`: Defaults to `us.amazon.nova-lite-v1:0` but can be customized in your config. For more info see: https://docs.aws.amazon.com/bedrock/latest/userguide/inference-profiles-support.html
- `profile`: Select which AWS profile should be used.

## `3` Run locally

To run the "Finder" agent, navigate to the example directory and execute:

```bash
cd examples/model_providers/mcp_basic_bedrock_agent

uv run main.py
```
