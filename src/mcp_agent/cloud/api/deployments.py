"""
API handlers for deployments in MCP Agent Cloud.

This module provides the handlers for the deployments API endpoints, including
utility and app deployments, listing, details, logs, and deletion.
"""

import asyncio
import json
import logging
import os
import tempfile
import time
import uuid
import zipfile
from pathlib import Path
from typing import Dict, List, Optional, Any, Union, Type

from aiohttp import web
from aiohttp.web import Request, Response
from pydantic import ValidationError, TypeAdapter

from ..deployment.containers.mcp_server_types import (
    DeploymentStatus,
    DeploymentType,
    STDIOServerConfig,
    SSEServerConfig,
    AgentAppServerConfig,
    STDIOServerConfigInput,
    SSEServerConfigInput,
    AgentAppServerConfigInput,
    ServerDeploymentRecord
)
from ..deployment.containers.service import (
    DockerContainerService,
    ImageBuildError,
    ContainerRunError,
    ReadinessCheckError,
    ContainerError
)
from ..deployment.registry import JsonServerRegistry

# Configure logger
logger = logging.getLogger("mcp_cloud.api.deployments")


class DeploymentsAPI:
    """
    Handlers for deployments API endpoints.
    
    This class provides the handlers for creating, listing, retrieving details,
    retrieving logs, and deleting deployments.
    """
    
    def __init__(self, registry: JsonServerRegistry, container_service: DockerContainerService):
        """
        Initialize the deployments API handlers.
        
        Args:
            registry: The deployment registry
            container_service: The container service
        """
        self.registry = registry
        self.container_service = container_service
    
    async def deploy_utility(self, request: Request) -> Response:
        """
        Deploy a utility server.
        
        Args:
            request: The HTTP request
            
        Returns:
            HTTP response
        """
        logger.info("Handling deploy utility request")
        
        try:
            # Parse request body
            body = await request.json()
            
            # Determine if this is a STDIO or SSE server based on presence of adapter_port or server_port
            is_stdio = "adapter_port" in body
            
            # Validate request body against the appropriate schema
            if is_stdio:
                logger.debug("Validating STDIO server config")
                utility_input = STDIOServerConfigInput(**body)
                config = STDIOServerConfig(
                    name=utility_input.name,
                    description=utility_input.description,
                    deployment_type=DeploymentType.UTILITY,
                    transport="stdio",
                    command=utility_input.command,
                    adapter_port=utility_input.adapter_port
                )
            else:
                logger.debug("Validating SSE server config")
                utility_input = SSEServerConfigInput(**body)
                config = SSEServerConfig(
                    name=utility_input.name,
                    description=utility_input.description,
                    deployment_type=DeploymentType.UTILITY,
                    transport="sse",
                    command=utility_input.command,
                    server_port=utility_input.server_port
                )
            
            # Generate unique ID for this deployment
            deployment_id = f"util-{int(time.time())}-{uuid.uuid4().hex[:8]}"
            
            # Generate API key for the server
            api_key = self.container_service._generate_api_key()
            
            # Register deployment in registry
            await self.registry.register(
                id=deployment_id,
                name=config.name,
                description=config.description,
                config=config,
                api_key=api_key,  # This will be hashed by the registry
                status=DeploymentStatus.BUILDING
            )
            
            # Build and run the server
            try:
                result = await self.container_service.build_and_run_utility(config)
                
                # Update registry with container details
                await self.registry.update_status(
                    id=deployment_id,
                    status=DeploymentStatus.RUNNING,
                    container_id=result["container_id"],
                    image_id=result["image_id"],
                    host_port=result["host_port"],
                    url=result["url"]
                )
                
                # Get the final deployment record for the response
                deployment = await self.registry.get(deployment_id)
                if not deployment:
                    raise Exception(f"Deployment not found after registration: {deployment_id}")
                
                # Create response data
                response_data = deployment.model_dump()
                
                # Replace hashed API key with plaintext key
                response_data["api_key"] = api_key
                
                return web.json_response(response_data, status=201)
            except (ImageBuildError, ContainerRunError, ReadinessCheckError) as e:
                logger.error(f"Error deploying utility server: {e}")
                
                # Update registry with error status
                await self.registry.update_status(
                    id=deployment_id,
                    status=DeploymentStatus.ERROR,
                    error=str(e)
                )
                
                return web.json_response(
                    {"error": "Failed to deploy utility server", "details": str(e)},
                    status=500
                )
                
        except ValidationError as e:
            logger.error(f"Validation error: {e}")
            return web.json_response(
                {"error": "Invalid utility server configuration", "details": e.errors()},
                status=400
            )
        except Exception as e:
            logger.error(f"Unexpected error: {e}")
            return web.json_response(
                {"error": "Unexpected error", "details": str(e)},
                status=500
            )
    
    async def deploy_app(self, request: Request) -> Response:
        """
        Deploy an Agent App as MCP Server.
        
        Args:
            request: The HTTP request
            
        Returns:
            HTTP response
        """
        logger.info("Handling deploy app request")
        
        temp_dir = None
        
        try:
            # Parse multipart request
            reader = await request.multipart()
            
            # Read config part
            config_part = await reader.next()
            if not config_part or config_part.name != "config":
                return web.json_response(
                    {"error": "Missing 'config' part in multipart request"},
                    status=400
                )
            
            config_str = await config_part.text()
            config_data = json.loads(config_str)
            
            # Read package part
            package_part = await reader.next()
            if not package_part or package_part.name != "package":
                return web.json_response(
                    {"error": "Missing 'package' part in multipart request"},
                    status=400
                )
            
            # Validate config against schema
            app_input = AgentAppServerConfigInput(**config_data)
            config = AgentAppServerConfig(
                name=app_input.name,
                description=app_input.description,
                deployment_type=DeploymentType.APP,
                entrypoint=app_input.entrypoint,
                app_port=app_input.app_port,
                http_path_prefix=app_input.http_path_prefix,
                dependencies=app_input.dependencies
            )
            
            # Generate unique ID for this deployment
            deployment_id = f"app-{int(time.time())}-{uuid.uuid4().hex[:8]}"
            
            # Generate API key for the server
            api_key = self.container_service._generate_api_key()
            
            # Register deployment in registry (status: packaging)
            await self.registry.register(
                id=deployment_id,
                name=config.name,
                description=config.description,
                config=config,
                api_key=api_key,  # This will be hashed by the registry
                status=DeploymentStatus.PACKAGING
            )
            
            # Create temp directory for package extraction
            temp_dir = tempfile.mkdtemp(prefix="mcp_cloud_app_package_")
            logger.debug(f"Created temp directory for package: {temp_dir}")
            
            # Save the package to temp directory
            package_file = os.path.join(temp_dir, "package.zip")
            with open(package_file, 'wb') as f:
                while True:
                    chunk = await package_part.read_chunk()
                    if not chunk:
                        break
                    f.write(chunk)
            
            # Extract the package
            extract_dir = os.path.join(temp_dir, "extracted_code")
            os.makedirs(extract_dir, exist_ok=True)
            
            try:
                with zipfile.ZipFile(package_file, 'r') as zip_ref:
                    zip_ref.extractall(extract_dir)
                logger.debug(f"Extracted package to: {extract_dir}")
            except zipfile.BadZipFile as e:
                raise ValueError(f"Invalid zip file: {e}")
            
            # Set the source path in the config
            config.source_path = extract_dir
            
            # Update registry status to building
            await self.registry.update_status(
                id=deployment_id,
                status=DeploymentStatus.BUILDING
            )
            
            # Build and run the app
            try:
                result = await self.container_service.build_and_run_app(config)
                
                # Update registry with container details
                await self.registry.update_status(
                    id=deployment_id,
                    status=DeploymentStatus.RUNNING,
                    container_id=result["container_id"],
                    image_id=result["image_id"],
                    host_port=result["host_port"],
                    url=result["url"]
                )
                
                # Get the final deployment record for the response
                deployment = await self.registry.get(deployment_id)
                if not deployment:
                    raise Exception(f"Deployment not found after registration: {deployment_id}")
                
                # Create response data
                response_data = deployment.model_dump()
                
                # Replace hashed API key with plaintext key
                response_data["api_key"] = api_key
                
                return web.json_response(response_data, status=201)
            except (ImageBuildError, ContainerRunError, ReadinessCheckError) as e:
                logger.error(f"Error deploying app: {e}")
                
                # Update registry with error status
                await self.registry.update_status(
                    id=deployment_id,
                    status=DeploymentStatus.ERROR,
                    error=str(e)
                )
                
                return web.json_response(
                    {"error": "Failed to deploy app", "details": str(e)},
                    status=500
                )
                
        except ValidationError as e:
            logger.error(f"Validation error: {e}")
            return web.json_response(
                {"error": "Invalid app configuration", "details": e.errors()},
                status=400
            )
        except ValueError as e:
            logger.error(f"Value error: {e}")
            return web.json_response(
                {"error": str(e)},
                status=400
            )
        except Exception as e:
            logger.error(f"Unexpected error: {e}")
            return web.json_response(
                {"error": "Unexpected error", "details": str(e)},
                status=500
            )
        finally:
            # Clean up temp directory
            if temp_dir and os.path.exists(temp_dir):
                try:
                    import shutil
                    shutil.rmtree(temp_dir)
                    logger.debug(f"Cleaned up temp directory: {temp_dir}")
                except Exception as e:
                    logger.error(f"Error cleaning up temp directory: {e}")
    
    async def list_deployments(self, request: Request) -> Response:
        """
        List all deployments.
        
        Args:
            request: The HTTP request
            
        Returns:
            HTTP response
        """
        logger.info("Handling list deployments request")
        
        try:
            # Get all deployments from registry
            deployments = await self.registry.list_all()
            
            # Create response data (don't include api_key)
            response_data = []
            for deployment in deployments:
                if deployment:  # Add a check to ensure deployment is not None
                    data = deployment.model_dump()
                    data.pop("api_key", None)  # Remove API key
                    response_data.append(data)
            
            return web.json_response(response_data)
        except Exception as e:
            logger.error(f"Error listing deployments: {e}")
            return web.json_response(
                {"error": "Failed to list deployments", "details": str(e)},
                status=500
            )
    
    async def get_deployment(self, request: Request) -> Response:
        """
        Get deployment details.
        
        Args:
            request: The HTTP request
            
        Returns:
            HTTP response
        """
        logger.info("Handling get deployment request")
        
        # Get deployment ID from path
        deployment_id = request.match_info.get("id")
        if not deployment_id:
            return web.json_response(
                {"error": "Missing deployment ID"},
                status=400
            )
        
        try:
            # Get deployment from registry
            deployment = await self.registry.get(deployment_id)
            if not deployment:
                return web.json_response(
                    {"error": f"Deployment not found: {deployment_id}"},
                    status=404
                )
            
            # Create response data
            response_data = deployment.model_dump()
            
            # Don't include API key in response
            response_data.pop("api_key", None)
            
            return web.json_response(response_data)
        except Exception as e:
            logger.error(f"Error getting deployment: {e}")
            return web.json_response(
                {"error": "Failed to get deployment", "details": str(e)},
                status=500
            )
    
    async def delete_deployment(self, request: Request) -> Response:
        """
        Delete a deployment.
        
        Args:
            request: The HTTP request
            
        Returns:
            HTTP response
        """
        logger.info("Handling delete deployment request")
        
        # Get deployment ID from path
        deployment_id = request.match_info.get("id")
        if not deployment_id:
            return web.json_response(
                {"error": "Missing deployment ID"},
                status=400
            )
        
        try:
            # Get deployment from registry
            deployment = await self.registry.get(deployment_id)
            if not deployment:
                return web.json_response(
                    {"error": f"Deployment not found: {deployment_id}"},
                    status=404
                )
            
            # Stop and remove container if it exists
            container_id = deployment.container_id
            if container_id:
                try:
                    await self.container_service.stop_and_remove(container_id)
                except ContainerError as e:
                    logger.warning(f"Error stopping container: {e}")
                    # Continue with removal
            
            # Remove deployment from registry
            await self.registry.remove(deployment_id)
            
            # Return success response
            return web.Response(status=204)
        except Exception as e:
            logger.error(f"Error deleting deployment: {e}")
            return web.json_response(
                {"error": "Failed to delete deployment", "details": str(e)},
                status=500
            )
    
    async def get_deployment_logs(self, request: Request) -> Response:
        """
        Get logs for a deployment.
        
        Args:
            request: The HTTP request
            
        Returns:
            HTTP response
        """
        logger.info("Handling get deployment logs request")
        
        # Get deployment ID from path
        deployment_id = request.match_info.get("id")
        if not deployment_id:
            return web.json_response(
                {"error": "Missing deployment ID"},
                status=400
            )
        
        # Get tail parameter
        tail_str = request.query.get("tail", "100")
        try:
            tail = int(tail_str)
        except ValueError:
            return web.json_response(
                {"error": "Invalid 'tail' parameter. Must be an integer."},
                status=400
            )
        
        try:
            # Get deployment from registry
            deployment = await self.registry.get(deployment_id)
            if not deployment:
                return web.json_response(
                    {"error": f"Deployment not found: {deployment_id}"},
                    status=404
                )
            
            # Get container ID
            container_id = deployment.container_id
            if not container_id:
                return web.json_response(
                    {"error": f"Deployment has no associated container: {deployment_id}"},
                    status=409
                )
            
            # Get logs from container
            logs = await self.container_service.get_logs(container_id, tail)
            
            # Return logs as plain text
            return web.Response(text=logs, content_type="text/plain")
        except ContainerError as e:
            if "not found" in str(e).lower():
                return web.json_response(
                    {"error": f"Container not found: {e}"},
                    status=404
                )
            else:
                return web.json_response(
                    {"error": f"Container error: {e}"},
                    status=500
                )
        except Exception as e:
            logger.error(f"Error getting deployment logs: {e}")
            return web.json_response(
                {"error": "Failed to get deployment logs", "details": str(e)},
                status=500
            )