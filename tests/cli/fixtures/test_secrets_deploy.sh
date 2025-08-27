#!/bin/bash
# Example script demonstrating the deploy command with secrets file processing

# Set required environment variables for secrets
export OPENAI_API_KEY="sk-openai-test-key"
export ANTHROPIC_API_KEY="sk-anthropic-test-key"

# Set API credentials
export MCP_API_BASE_URL="http://localhost:3000/api"
export MCP_API_KEY="your-api-key"

# Run deploy with secrets file (dry run mode)
python -m mcp_agent.cli.cli.main deploy \
  --dry-run \
  tests/fixtures/example_config.yaml \
  --secrets-file tests/fixtures/example_secrets.yaml \
  --secrets-output-file tests/fixtures/example_secrets.transformed.yaml

# Note: In a real environment, these environment variables would be securely managed,
# and the API token would be obtained through proper authentication.