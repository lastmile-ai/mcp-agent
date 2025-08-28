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

1. **Developer Secrets** (`!developer_secret`):

   - Used for secrets that are provided by developers
   - Values are known at deployment time
   - Example: API keys, service credentials, etc.

2. **User Secrets** (`!user_secret`):
   - Used for secrets that will be provided by users
   - Values are not known at deployment time
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
  key: !developer_secret API_KEY # Developer provides value through API_KEY environment variable

database:
  # User will provide this later - no environment variable specified
  password: !user_secret
```

When processed during deployment, the secrets file is transformed into:

```yaml
# mcp_agent.deployed.secrets.yaml
api:
  key: mcpac_sc_123e4567-e89b-12d3-a456-426614174000  # Developer secret transformed to UUID

database:
  password: !user_secret  # User secret with no env var name remains as a tag
```

Then, during app configuration, the user configuring the app will specify values for each of the required secrets.

## Usage

### Command Line Interface

#### Deploying an App

```bash
# Basic usage (requires both config and secrets files)
mcp-agent deploy <app_name> --secrets-file mcp_agent.secrets.yaml

# With custom output path for transformed secrets
mcp-agent deploy <app_name> --secrets-file mcp_agent.secrets.yaml --secrets-output-file mcp_agent.deployed.secrets.yaml

# With explicit API URL and key
mcp-agent deploy <app_name> --secrets-file mcp_agent.secrets.yaml --api-url=https://mcp-api.example.com --api-key=your-api-key

# Dry run mode (for testing)
mcp-agent deploy <app_name> --secrets-file mcp_agent.secrets.yaml --dry-run

# Help information
mcp-agent --help
mcp-agent deploy --help
```

#### Configuring an App

```bash
# Basic usage
mcp-agent configure <app_id or app_server_url>

# With existing processed secrets file
mcp-agent configure <app_id or app_server_url> -s mcp_agent.configured.secrets.yaml

# With custom processed secrets output file
mcp-agent configure <app_id or app_server_url> -o my_mcp_agent.configured.secrets.yaml

# With explicit API URL and key
mcp-agent configure <app_id or app_server_url> --api-url=https://mcp-api.example.com --api-key=your-api-key

# Dry run mode (for testing)
mcp-agent configure <app_id or app_server_url> --dry-run
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
   config_file="path/to/mcp_agent.config.yaml",
   secrets_file="path/to/mcp_agent.secrets.yaml",
   secrets_output_file="path/to/output_secrets.yaml",
   api_url="https://mcp-api.example.com",
   api_key="your-api-key",
   dry_run=True
)
```

### Direct Secrets API Usage

You can also use the secrets API client directly:

```python
from mcp_agent.cli.secrets.api_client import SecretsClient
from mcp_agent.cli.secrets.constants import SecretType

# Initialize client
client = SecretsClient(
   api_url="https://mcp-api.example.com",
   api_key="your-api-key"
)

# Create a developer secret
secret_id = await client.create_secret(
   name="api.key",
   secret_type=SecretType.DEVELOPER,
   value="secret-value"
)
print(f"Created developer secret with ID: {secret_id}")

# Create a user secret (placeholder)
user_secret_id = await client.create_secret(
   name="database.password",
   secret_type=SecretType.USER,
   value=""  # Empty string for user secrets
)
print(f"Created user secret placeholder with ID: {user_secret_id}")

# Get a secret value
value = await client.get_secret_value(secret_id)
print(f"Secret value: {value}")

# Set a value for a user secret
await client.set_secret_value(user_secret_id, "user-provided-value")
```

## Integration in Other CLIs

The MCP Agent Cloud commands can be integrated into other CLIs:

```python
import typer
from mcp_agent.cli.cloud.commands import deploy_config

app = typer.Typer()

# Add the cloud deploy command directly
# You'll need to update the @app.command decorator to match the new parameter requirements
app.command(name="cloud-deploy")(deploy_config)
```

## Testing

### Unit Tests

The cloud sdk tests are part of the mcp-agent test suite.

```bash
# Run all tests
uv run pytest

# Run only unit tests for the cloud sdk
uv run pytest tests/cloud
```

