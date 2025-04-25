"""MCP Agent Cloud command functions.

This package contains the core functionality of the MCP Agent Cloud commands.
Each command is exported as a single function with a signature that matches the CLI interface.
"""

from .deploy.main import deploy_config
from .login import login

__all__ = ["deploy_config", "login"]
