# Secret Management in MCP Agent Cloud

This document explains how to use the MCP Agent Cloud CLI to manage secrets in your applications.

## Overview

MCP Agent Cloud provides a robust secrets management system that:

1. Identifies secrets in your configuration using YAML tags
2. Stores secrets securely in a central backend
3. Replaces secret values with opaque secret IDs in your configuration
4. Resolves those secret IDs to actual values at runtime

## Secret Types

There are two types of secrets:

- **Developer Secrets**: Values known at deploy time, provided by the application developer
- **User Secrets**: Values collected from end-users at runtime, not known during deployment

## Identifying Secrets in Configuration

Use YAML tags to mark secrets in your configuration:

```yaml
# Developer secret with a value
api_key: !developer_secret my-api-key-value

# Developer secret from environment variable
api_key: !developer_secret ${oc.env:API_KEY}

# User secret (placeholder, no value yet)
user_token: !user_secret
```

## Secret Files

Following the established pattern in MCP Agent, secrets are managed using a dedicated `mcp_agent.secrets.yaml` file, separate from the main configuration.

This approach:
- Keeps sensitive information separate from regular configuration
- Allows you to gitignore the secrets file for security
- Creates a clear separation between configuration and credentials

The standard pattern for MCP Agent projects:
1. Keep all regular configuration in `mcp_agent.config.yaml`
2. Keep all secrets in `mcp_agent.secrets.yaml`

This separation is enforced by the CLI, which requires a separate secrets file for deployment.

## Deployment Process

When you deploy your application with `mcp-agent deploy`, the CLI:

1. Detects all tagged secrets in your configuration and secrets file
2. For developer secrets, collects the values (from tags or environment variables)
3. Creates secret records in the backend API
4. Transforms your files, replacing tags with database-generated secret IDs (UUIDs)
5. Stores the transformed files for use during runtime

### Example

```bash
# Standard deployment
mcp-agent deploy \
  mcp_agent.config.yaml \
  --secrets-file mcp_agent.secrets.yaml

# Specifying custom output path for transformed secrets
mcp-agent deploy \
  mcp_agent.config.yaml \
  --secrets-file mcp_agent.secrets.yaml \
  --secrets-output-file mcp_agent.secrets.deployed.yaml
```

## Configuration vs Runtime Phases

After deployment, your transformed configuration contains only secret IDs, not actual secret values. The full secrets workflow involves:

1. **Deploy**: Transform tags to secret IDs, store developer secrets
2. **Configure**: Collect and store user secrets (future functionality)
3. **Run**: Resolve all secret IDs to actual values at runtime (future functionality)

## Current Limitations

The current implementation supports:
- Tag detection and transformation
- Developer and user secret registration
- Separate secrets file processing

Future releases will add:
- `configure` command for user secret collection
- Runtime secret resolution
- Enhanced security and permission controls

## Technical Details

### Secret Types vs API Design

While the CLI distinguishes between developer and user secrets:
- Developer secrets: Values known at deploy time
- User secrets: Values collected at configure time

The backend API itself doesn't have this distinction. From the API's perspective, all secrets are just "secrets" with a name and value. The SDK maintains this developer/user distinction locally for better UX, but doesn't transmit this typing information to the API.

For user secrets, we store an empty string value initially, which will be replaced with the actual value during the configure phase.