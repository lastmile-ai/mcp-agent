"""MCP Agent Cloud command functions.

This package contains the core functionality of the MCP Agent Cloud commands.
Each command is exported as a single function with a signature that matches the CLI interface.
"""

from .configure.main import configure_app
from .deploy.main import deploy_config
from .auth import login, logout, whoami

__all__ = ["configure_app", "deploy_config", "login", "logout", "whoami"]
