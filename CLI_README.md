# MCP Agent Cloud SDK

The MCP Agent Cloud SDK provides a command-line tool and Python library for deploying and managing MCP Agent configurations, with integrated secrets handling.

## Features

- Deploy MCP Agent configurations
- Process secret tags in configuration files
- Interact with Vault for secure secrets storage
- Support for developer and user secrets

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
│       │   ├── direct_vault_client.py
│       │   ├── factory.py
│       │   ├── http_client.py
│       │   ├── interface.py
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

## Usage

### Command Line Interface

```bash
# Basic usage
mcp-agent deploy config.yaml

# With direct vault integration
VAULT_ADDR=http://localhost:8200 VAULT_TOKEN=root mcp-agent deploy config.yaml --secrets-mode=direct_vault

# Help information
mcp-agent --help
mcp-agent deploy --help
```

### As a Library

```python
from mcp_agent_cloud.commands import deploy_config

# Deploy a configuration
deploy_config(
    config_file="path/to/config.yaml",
    secrets_mode="direct_vault",
    vault_addr="http://localhost:8200",
    vault_token="your-token",
    dry_run=True
)
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
app.command(name="cloud-deploy")(deploy_config)
```

## Testing

```bash
# Run all tests
uv run pytest

# Run only unit tests for the secrets module
uv run pytest tests/secrets/

# Run integration tests that require a real Vault instance
uv run pytest -m vault_integration
```