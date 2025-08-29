#!/bin/bash
# Test script for the mcp-agent deploy command

# Set the working directory to the repository root
cd "$(dirname "$0")/../.."

# Ensure Vault is running (if using direct_vault mode)
export VAULT_ADDR=${VAULT_ADDR:-"http://localhost:8200"}
export VAULT_TOKEN=${VAULT_TOKEN:-"root"}  # Development/test token

# Set environment variables for test
export MCP_BEDROCK_API_KEY="test-bedrock-api-key"

# Run the deploy command with dry-run flag
python -m mcp_agent_cli.cli deploy tests/fixtures/bedrock_config.yaml --dry-run

# Run with direct_vault mode explicitly
python -m mcp_agent_cli.cli deploy tests/fixtures/bedrock_config.yaml --secrets-mode=direct_vault --dry-run