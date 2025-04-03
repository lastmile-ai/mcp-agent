"""
API server for MCP Agent Cloud.

This module provides the main entry point for the API server,
setting up the web application, routes, middleware, and services.
"""

import asyncio
import logging
import os
from pathlib import Path

from aiohttp import web

from ..deployment.containers.service import DockerContainerService
from ..deployment.registry import JsonServerRegistry
from ..log_config import setup_logging
from .auth import MasterApiKeyAuthenticator, master_auth_middleware
from .deployments import DeploymentsAPI

# Configure logger
logger = logging.getLogger("mcp_cloud.api.server")


async def handle_health(request: web.Request) -> web.Response:
    """
    Handle health check requests.
    
    Args:
        request: The HTTP request
        
    Returns:
        HTTP 200 OK response with status="ok"
    """
    return web.json_response({"status": "ok"})


def create_app() -> web.Application:
    """
    Create and configure the web application.
    
    Returns:
        Configured aiohttp web application
    """
    # Create services
    try:
        # Initialize the registry
        registry = JsonServerRegistry()
        
        # Initialize the container service
        container_service = DockerContainerService()
        
        # Check Docker connectivity
        container_service.client.ping()
        
        # Initialize the deployments API
        deployments_api = DeploymentsAPI(registry, container_service)
        
        # Initialize the authenticator to load key from environment
        authenticator = MasterApiKeyAuthenticator()
        
        # Create the web application
        app = web.Application(middlewares=[master_auth_middleware])
        
        # Store services in app
        app["registry"] = registry
        app["container_service"] = container_service
        app["deployments_api"] = deployments_api
        app["authenticator"] = authenticator
        
        # Set up routes
        app.add_routes([
            web.get("/health", handle_health),
            web.post("/deployments/utility", deployments_api.deploy_utility),
            web.post("/deployments/app", deployments_api.deploy_app),
            web.get("/deployments", deployments_api.list_deployments),
            web.get("/deployments/{id}", deployments_api.get_deployment),
            web.delete("/deployments/{id}", deployments_api.delete_deployment),
            web.get("/deployments/{id}/logs", deployments_api.get_deployment_logs),
        ])
        
        return app
    except Exception as e:
        logger.critical(f"Failed to create application: {e}")
        raise


async def check_docker() -> bool:
    """
    Check if Docker is available and running.
    
    Returns:
        True if Docker is available, False otherwise
    """
    try:
        # Initialize Docker container service
        container_service = DockerContainerService()
        # Check connectivity
        container_service.client.ping()
        logger.info("Docker is available and running")
        return True
    except Exception as e:
        logger.critical(f"Docker is not available: {e}")
        return False



def main():
    """
    Main entry point for the API server.
    
    Sets up logging, creates the web application, and runs the server.
    """
    # Set up logging
    setup_logging()
    
    # Log startup
    logger.info("Starting MCP Agent Cloud API server")
    
    # Load environment variables from .env file
    try:
        from dotenv import load_dotenv
        load_dotenv()
        logger.info("Environment variables loaded from .env file")
    except ImportError:
        logger.warning("python-dotenv not installed. Skipping .env file loading.")
    except Exception as e:
        logger.error(f"Error loading .env file: {e}")
    
    # Check Docker availability
    loop = asyncio.get_event_loop()
    if not loop.run_until_complete(check_docker()):
        logger.critical("Docker is required but not available. Exiting.")
        return 1
    
    # Create application
    try:
        app = create_app()
    except Exception as e:
        logger.critical(f"Failed to create application: {e}")
        return 1
    
    # Get server configuration from environment
    host = os.environ.get("MCP_CLOUD_API_HOST", "localhost")
    port = int(os.environ.get("MCP_CLOUD_API_PORT", "8080"))
    
    # Run the server
    logger.info(f"Starting server on http://{host}:{port}")
    web.run_app(app, host=host, port=port, access_log=None)
    
    # This is only reached when the server is stopped
    logger.info("Server stopped")
    return 0


if __name__ == "__main__":
    exit(main())