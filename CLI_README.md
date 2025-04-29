# MCP Agent Cloud SDK

The MCP Agent Cloud SDK provides a command-line tool and Python library for deploying and managing MCP Agent configurations, with integrated secrets handling.

## Features

- Deploy MCP Agent configurations
- Process secret tags in configuration files
- Securely manage secrets through the MCP Agent Cloud API
- Support for developer and user secrets
- Enhanced UX with rich formatting and intuitive prompts
- Detailed logging with minimal console output

## Project Structure

```
mcp-agent-cloud/py/sdk-cloud/
├── README.md
├── pyproject.toml
├── src/
│   └── mcp_agent_cloud/      # Core package
│       ├── __init__.py
│       ├── cli/              # CLI implementation
│       │   ├── __init__.py
│       │   └── main.py       # Entry point that uses commands
│       ├── commands/         # Reusable command functions
│       │   ├── __init__.py
│       │   └── deploy.py     # Deploy command implementation
│       ├── config/           # Configuration handling
│       │   ├── __init__.py
│       │   └── settings.py
│       ├── secrets/          # Secrets handling
│       │   ├── __init__.py
│       │   ├── constants.py
│       │   ├── api_client.py # API-based secrets client
│       │   └── processor.py
│       └── ux.py
└── tests/                    # Test suite
```

## Installation

### Development Setup

```bash
# Navigate to the package root
cd mcp-agent-cloud/py/sdk-cloud

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
  key: !developer_secret ${oc.env:API_KEY} # Developer provides this value

database:
  password: !user_secret # User will provide this later
```

When processed during deployment, the secrets file is transformed into:

```yaml
# mcp_agent.secrets.yaml.transformed.yaml
api:
  key: 123e4567-e89b-12d3-a456-426614174000

database:
  password: !user_secret
```

## Usage

### Command Line Interface

```bash
# Basic usage (requires both config and secrets files)
mcp-agent deploy mcp_agent.config.yaml --secrets-file mcp_agent.secrets.yaml

# With custom output path for transformed secrets
mcp-agent deploy mcp_agent.config.yaml --secrets-file mcp_agent.secrets.yaml --secrets-output-file secrets.deployed.yaml

# With explicit API URL and key
mcp-agent deploy mcp_agent.config.yaml --secrets-file mcp_agent.secrets.yaml --api-url=https://mcp-api.example.com --api-key=your-api-key

# Dry run mode (for testing)
mcp-agent deploy mcp_agent.config.yaml --secrets-file mcp_agent.secrets.yaml --dry-run

# Demo the enhanced UX
./demo_secrets_ux.sh

# Help information
mcp-agent --help
mcp-agent deploy --help
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
from mcp_agent_cloud.commands import deploy_config

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
from mcp_agent_cloud.secrets.api_client import SecretsClient
from mcp_agent_cloud.secrets.constants import SecretType

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

The MCP Agent Cloud commands can be integrated into other CLIs by using the `cloud` extra:

```bash
# Install with the cloud extra
pip install "mcp-agent-cloud[cloud]"
```

```python
import typer
from mcp_agent_cloud.commands import deploy_config

app = typer.Typer()

# Add the cloud deploy command directly
# You'll need to update the @app.command decorator to match the new parameter requirements
app.command(name="cloud-deploy")(deploy_config)
```

## Testing

### Unit Tests

```bash
# Run all tests
uv run pytest

# Run only unit tests for the secrets module
uv run pytest tests/secrets/
```

### Integration Tests

Integration tests require a running instance of the web app with Secret API enabled:

1. Start the web app:

   ```bash
   cd www && pnpm run dev
   # or for a complete setup including database and API services
   cd www && pnpm run webdev
   ```

2. Run the integration tests:

   ```bash
   # Using the convenience script that checks prerequisites
   ./scripts/run_integration_tests.sh

   # Or manually set up environment and run tests
   export MCP_API_BASE_URL="http://localhost:3000/api"
   export MCP_API_KEY="your-api-key"

   # Run all integration tests
   uv run pytest -m integration -v

   # Run specific test files
   uv run pytest tests/integration/test_secrets_api_integration.py -v  # API client tests
   uv run pytest tests/integration/test_mcp_agent_configs.py -v        # CLI integration tests
   ```

The integration tests verify:

1. **API Integration Tests:** Test that the `SecretsClient` can properly interact with the web app's secrets API, including creating, reading, updating, listing, and deleting secrets.

2. **CLI Integration Tests:** Test that the `mcp-agent deploy` command properly processes secrets files, transforms them, and interacts with the Secrets API correctly, including:
   - Processing secrets files with developer and user secrets
   - Processing developer secrets with values from environment variables
   - Processing user secrets (placeholders)
   - Validation for developer secrets (must have values)
   - Handling error cases like missing credentials

## Secret Management Workflow

The complete secrets workflow consists of three phases:

1. **Deploy** (implemented):

   - Process the dedicated secrets file
   - Transform all secret tags to Prisma IDs
   - Store developer secrets in the backend
   - Create placeholders for user secrets

2. **Configure** (future):

   - Load the transformed secrets file (containing IDs)
   - Prompt for values for user secrets
   - Store those values in the backend
   - The secrets file remains unchanged (IDs only)

3. **Run** (future):
   - Load the transformed secrets file
   - Fetch all secret values from the backend
   - Inject them into the application environment
