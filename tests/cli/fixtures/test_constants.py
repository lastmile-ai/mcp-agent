"""Test constants for MCP Agent Cloud tests.

This file contains constants that are used across multiple test files.
"""

from mcp_agent.cli.core.constants import UUID_PREFIX

# Test UUIDs with proper prefix pattern
TEST_SECRET_UUID = f"{UUID_PREFIX}11111111-1111-1111-1111-111111111111"
BEDROCK_API_KEY_UUID = f"{UUID_PREFIX}22222222-2222-2222-2222-222222222222"
DATABASE_PASSWORD_UUID = f"{UUID_PREFIX}33333333-3333-3333-3333-333333333333"
OPENAI_API_KEY_UUID = f"{UUID_PREFIX}44444444-4444-4444-4444-444444444444"
ANTHROPIC_API_KEY_UUID = f"{UUID_PREFIX}55555555-5555-5555-5555-555555555555"

# Common paths for testing
TEST_CONFIG_PATH = "/tmp/test-config.yaml"
TEST_SECRETS_PATH = "/tmp/test-secrets.yaml"
TEST_OUTPUT_PATH = "/tmp/test-output.yaml"

# Sample config for testing
SAMPLE_CONFIG = """
server:
  host: localhost
  port: 8000
"""

# Sample secrets config for testing
SAMPLE_SECRETS = """
api:
  keys:
    bedrock: !developer_secret BEDROCK_API_KEY
    openai: !developer_secret OPENAI_API_KEY
    anthropic: !user_secret
database:
  password: !developer_secret DB_PASSWORD
"""

# Sample transformed secrets for testing
SAMPLE_TRANSFORMED_SECRETS = f"""
api:
  keys:
    bedrock: {BEDROCK_API_KEY_UUID}
    openai: {OPENAI_API_KEY_UUID}
    anthropic: !user_secret
database:
  password: {DATABASE_PASSWORD_UUID}
"""
