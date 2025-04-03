"""
Logging configuration for MCP Agent Cloud.

This module configures the Python logging system for use by all cloud components.
It sets up consistent formatting and log levels based on environment variables.
"""

import logging
import os
from datetime import datetime, timezone

def setup_logging():
    """
    Configure the logging system for MCP Agent Cloud.
    
    Uses LOG_LEVEL environment variable to set the logging level.
    Default level is DEBUG during development.
    
    Returns:
        logging.Logger: The configured root logger.
    """
    log_level_str = os.getenv("LOG_LEVEL", "DEBUG").upper()
    log_level = getattr(logging, log_level_str, logging.DEBUG)
    
    # Configure the root logger with consistent formatting
    logging.basicConfig(
        level=log_level,
        format='%(asctime)s [%(name)s] %(levelname)-8s: %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S %z',
        force=True  # Override any existing configuration
    )
    
    # Create a logger for MCP Cloud components
    logger = logging.getLogger("mcp_cloud")
    logger.setLevel(log_level)
    
    # Log startup information
    logger.info(f"Logging initialized at {datetime.now(timezone.utc).isoformat()} (UTC)")
    logger.info(f"Log level set to {log_level_str}")
    
    return logger