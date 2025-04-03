"""
Agent App runner for MCP Agent Cloud.

This script is the entry point for Agent App containers. It loads the MCPApp
instance from the entrypoint and serves it as an MCP Server.
"""

import importlib
import logging
import os
import signal
import sys
from pathlib import Path

# Configure logging
LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO").upper()
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL),
    format='%(asctime)s [agent_app_runner] %(levelname)-8s: %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
    stream=sys.stdout,
    force=True
)
logger = logging.getLogger("agent_app_runner")


def handle_signal(signum, frame):
    """
    Handle termination signals for graceful shutdown.
    
    Args:
        signum: Signal number
        frame: Current stack frame
    """
    signal_name = {
        signal.SIGINT: "SIGINT",
        signal.SIGTERM: "SIGTERM"
    }.get(signum, f"signal {signum}")
    
    logger.info(f"Received {signal_name}, initiating graceful shutdown...")
    # System exit will trigger cleanup in the main function
    sys.exit(0)


def main():
    """
    Main entry point for the Agent App runner.
    
    Loads the MCPApp instance from the entrypoint and serves it as an MCP Server.
    """
    # Setup signal handlers for graceful shutdown
    try:
        signal.signal(signal.SIGINT, handle_signal)
        signal.signal(signal.SIGTERM, handle_signal)
        logger.debug("Signal handlers registered for graceful shutdown")
    except Exception as e:
        logger.warning(f"Failed to set up signal handlers: {e}")
    
    # Import MCP Agent components
    try:
        from mcp_agent.app import MCPApp
        from mcp_agent.app_server import run_mcp_server_from_app_instance
    except ImportError as e:
        logger.critical(f"Failed to import mcp-agent components: {e}")
        return 1
    
    # Read configuration from environment variables
    entrypoint = os.environ.get("ENTRYPOINT")
    port_str = os.environ.get("PORT", "8000")
    api_key = os.environ.get("MCP_SERVER_API_KEY")
    http_path_prefix = os.environ.get("HTTP_PATH_PREFIX", "/mcp")
    
    # Validate configuration
    if not entrypoint:
        logger.critical("ENTRYPOINT environment variable not set")
        return 1
    
    try:
        port = int(port_str)
    except ValueError:
        logger.critical(f"Invalid PORT: {port_str}")
        return 1
    
    logger.info(f"Configuration: ENTRYPOINT={entrypoint}, PORT={port}, HTTP_PATH_PREFIX={http_path_prefix}, API_KEY={'present' if api_key else 'not set'}")
    
    # Log dependency environment variables (without exposing sensitive values)
    dependency_prefixes = ['FILESYSTEM_', 'FETCH_', 'OPENAI_']
    dependencies = []
    for key, value in os.environ.items():
        for prefix in dependency_prefixes:
            if key.startswith(prefix):
                if key.endswith('_API_KEY'):
                    # Log presence of API keys without exposing them
                    dependencies.append(f"{key}={'present' if value else 'not set'}")
                else:
                    dependencies.append(f"{key}={value}")
    
    if dependencies:
        logger.info(f"Found dependencies: {', '.join(dependencies)}")
    else:
        logger.warning("No recognized dependencies found in environment variables")
    
    # Add current directory to Python path
    sys.path.insert(0, str(Path.cwd()))
    
    # Parse entrypoint (module:variable)
    try:
        module_name, variable_name = entrypoint.split(":", 1)
    except ValueError:
        logger.critical(f"Invalid entrypoint format: {entrypoint}. Expected 'module:variable'.")
        return 1
    
    # Load the module
    try:
        logger.info(f"Loading module: {module_name}")
        module = importlib.import_module(module_name)
    except ModuleNotFoundError:
        logger.critical(f"Module not found: {module_name}")
        return 1
    except Exception as e:
        logger.critical(f"Error importing module: {e}")
        return 1
    
    # Get the variable
    try:
        logger.info(f"Getting variable: {variable_name}")
        app_instance = getattr(module, variable_name)
    except AttributeError:
        logger.critical(f"Variable not found in module: {variable_name}")
        return 1
    except Exception as e:
        logger.critical(f"Error getting variable: {e}")
        return 1
    
    # Verify it's an MCPApp
    if not isinstance(app_instance, MCPApp):
        logger.critical(f"Variable {variable_name} is not an MCPApp instance")
        return 1
    
    logger.info(f"Successfully loaded MCPApp: {app_instance.name}")
    
    # Run the app as an MCP Server
    try:
        logger.info(f"Starting MCP Server on port {port}")
        run_mcp_server_from_app_instance(
            app=app_instance,
            host="0.0.0.0",  # Listen on all interfaces
            port=port,
            api_key=api_key,
            path_prefix=http_path_prefix
        )
        # This should never be reached as the server runs until interrupted
        logger.info("MCP Server exited")
    except Exception as e:
        logger.critical(f"Error running MCP Server: {e}")
        return 1
    
    return 0


if __name__ == "__main__":
    sys.exit(main())