# MCP Agent Cloud SDK

The MCP Agent Cloud SDK provides a command-line tool and Python library for deploying and managing MCP Agent configurations, with integrated secrets handling.

## Features

- Deploy MCP Agent configurations
- Process secret tags in configuration files
- Securely manage secrets through the MCP Agent Cloud API
- Support for developer and user secrets
- Enhanced UX with rich formatting and intuitive prompts
- Detailed logging with minimal console output

## Installation

### Development Setup

```bash
# Navigate to the package root
# Create and activate a virtual environment
uv venv .venv
source .venv/bin/activate

# Install in editable mode with dev dependencies
uv pip install -e ".[dev]"
```

## Secrets Management

The SDK uses a streamlined approach to secrets management:

1. All secrets are managed through the MCP Agent Cloud API
2. The web application is the single source of truth for secret storage
3. Secret values are stored in HashiCorp Vault, but accessed only via the API

### Secret Types

Two types of secrets are supported:

1. **Developer Secrets**:

   - Used for secrets that are provided by developers when deploying an app
   - Values are known at deployment time and will be accessible at runtime on the deployed app
   - Example: API keys, service credentials, etc.

2. **User Secrets**:
   - Used for secrets that will be provided by users to 'configure' an instance of the app
   - Values are not known at original app deployment time
   - Example: User's database credentials, personal API keys, etc.

### Secret IDs

All secrets are referenced using database-generated IDs:

- These are UUID strings returned by the Secrets API
- Internal Vault handles are not exposed to clients

### Configuration Example

```yaml
# mcp_agent.config.yaml (main configuration file)
server:
  host: localhost
  port: 8000
# Note: Secrets are stored in a separate mcp_agent.secrets.yaml file
```

```yaml
# mcp_agent.secrets.yaml (separate secrets file)
api:
  key: sk-...

database:
  password: xk12...
```

When processed during deployment, the secrets file is transformed into:

```yaml
# mcp_agent.deployed.secrets.yaml
api:
  key: mcpac_sc_123e4567-e89b-12d3-a456-426614174000 # Deployment secret transformed to UUID

database:
  password: !user_secret # User secret to be required for configuring the app
```

In the above example, assume the developer selected user secret (2) when prompted for specifying the database.password secret type.

Then, during app configuration, the user configuring the app will specify values for the required secret.

## Usage

### Command Line Interface

#### Deploying an App

```bash
# Basic usage (requires both config and secrets files)
mcp-agent deploy <app_name> -c "path/to/project/configuration"

# Help information
mcp-agent --help
mcp-agent deploy --help
```

#### Configuring an App

```bash
# Basic usage
mcp-agent configure <app_id or app_server_url>
```

### Environment Variables

You can set these environment variables:

```bash
# API configuration
export MCP_API_BASE_URL=https://mcp-api.example.com
export MCP_API_KEY=your-api-key
```

### As a Library

```python
from mcp_agent.cli.cloud.commands import deploy_config

# Deploy a configuration
await deploy_config(
   app_name="My MCP Agent App"
   config_dir="path/to/project/configuration,
   api_key="your-api-key",
   non_interactive=True
)
```
