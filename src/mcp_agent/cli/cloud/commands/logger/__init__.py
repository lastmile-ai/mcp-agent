"""MCP Agent Cloud Logger commands.

This package contains functionality for configuring observability and retrieving/streaming logs
from deployed MCP apps.
"""

from .tail.main import tail_logs

__all__ = ["tail_logs"]
