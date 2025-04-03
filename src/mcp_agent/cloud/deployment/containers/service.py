"""
Docker container service for MCP Agent Cloud.

This module provides the DockerContainerService class which handles all
Docker-related operations for building and running containers for MCP servers.
"""

import asyncio
import logging
import os
import tempfile
import time
from pathlib import Path
from typing import Dict, List, Optional, Any, Union, Tuple

import docker
from docker.errors import APIError, DockerException, NotFound

from .mcp_server_types import (
    STDIOServerConfig,
    SSEServerConfig, 
    AgentAppServerConfig
)
from .template_manager import TemplateManager

# Configure logger
logger = logging.getLogger("mcp_cloud.container")


class ImageBuildError(Exception):
    """Raised when Docker image build fails."""
    pass


class ContainerRunError(Exception):
    """Raised when Docker container run fails."""
    pass


class ReadinessCheckError(Exception):
    """Raised when container readiness check fails."""
    pass


class ContainerError(Exception):
    """Raised for general container operations errors."""
    pass


class DockerContainerService:
    """
    Service for managing Docker containers for MCP Servers.
    
    This service handles building images, running containers, checking readiness,
    retrieving logs, and stopping/removing containers.
    """
    
    def __init__(self):
        """
        Initialize the Docker container service.
        
        Initializes Docker client and template manager.
        Validates Docker daemon connectivity.
        Locates local mcp-agent source path for Agent App deployments.
        """
        # Initialize Docker client
        try:
            self.client = docker.from_env()
            # Validate Docker connectivity
            self.client.ping()
            logger.info("Docker client connected successfully")
        except DockerException as e:
            logger.critical(f"Failed to connect to Docker: {e}")
            raise
        
        # Initialize template manager
        self.template_manager = TemplateManager()
        
        # Find local mcp-agent source path
        self.mcp_agent_src_path = self._find_mcp_agent_source()
        if not self.mcp_agent_src_path:
            logger.warning("Failed to locate mcp-agent source path. Agent App deployments may fail.")
    
    def _find_mcp_agent_source(self) -> Optional[str]:
        """
        Find the local mcp-agent source path.
        
        Returns:
            Path to the local mcp-agent source, or None if not found
        """
        # Start with the current file's location
        current_file = Path(__file__)
        # Navigate up to find src/mcp_agent
        try:
            # Assuming structure like .../src/mcp_agent/cloud/deployment/containers/service.py
            cloud_dir = current_file.parent.parent.parent
            mcp_agent_dir = cloud_dir.parent
            src_dir = mcp_agent_dir.parent
            
            # Verify this is indeed the mcp-agent source
            init_path = mcp_agent_dir / "__init__.py"
            if init_path.exists():
                logger.info(f"Found mcp-agent source at: {mcp_agent_dir}")
                return str(mcp_agent_dir)
        except Exception as e:
            logger.error(f"Error while looking for mcp-agent source: {e}")
        
        return None
    
    def _generate_api_key(self) -> str:
        """
        Generate a random API key for server authentication.
        
        Returns:
            Random API key string
        """
        import secrets
        return secrets.token_urlsafe(32)
    
    def _render_dockerfile(self, template_name: str, config: Dict[str, Any]) -> str:
        """
        Render a Dockerfile template with the given configuration.
        
        Args:
            template_name: Name of the template to render
            config: Dictionary of values to render into the template
            
        Returns:
            Rendered Dockerfile content
        """
        logger.debug(f"Rendering Dockerfile template: {template_name}")
        try:
            template = self.template_manager.render_template(template_name, config)
            return template
        except Exception as e:
            logger.error(f"Error rendering Dockerfile template: {e}")
            raise
    
    async def _build_image(self, context_path: str, tag: str) -> str:
        """
        Build a Docker image from a build context.
        
        This method runs the Docker build command in an executor to avoid blocking.
        
        Args:
            context_path: Path to the build context directory
            tag: Tag for the built image
            
        Returns:
            ID of the built image
            
        Raises:
            ImageBuildError: If the build fails
        """
        logger.info(f"Building Docker image with tag: {tag}")
        # Capture all build output for logging and error reporting
        build_logs = []
        
        def _sync_build_image():
            """Synchronous function to run in executor."""
            try:
                # Use the low-level API to get build logs
                for chunk in self.client.api.build(
                    path=context_path,
                    tag=tag,
                    rm=True,  # Remove intermediate containers
                    quiet=False,  # Get verbose output
                ):
                    if chunk:
                        # Decode chunk to string and parse
                        chunk_str = chunk.decode('utf-8', errors='replace')
                        build_logs.append(chunk_str)
                        
                        # Check for errors
                        if '"errorDetail"' in chunk_str or '"error"' in chunk_str:
                            logger.error(f"Docker build error: {chunk_str}")
                            raise ImageBuildError(f"Docker build failed: {chunk_str}")
                        
                        # Log progress
                        if '"stream"' in chunk_str:
                            log_line = chunk_str.strip()
                            logger.debug(f"Build: {log_line}")
                
                # Get the ID of the built image
                image = self.client.images.get(tag)
                logger.info(f"Docker image built successfully: {image.id}")
                return image.id
            except Exception as e:
                logger.error(f"Error building Docker image: {e}")
                raise ImageBuildError(f"Docker build failed: {e}\nBuild logs: {''.join(build_logs)}")
        
        # Run the build in an executor to avoid blocking
        loop = asyncio.get_event_loop()
        try:
            image_id = await loop.run_in_executor(None, _sync_build_image)
            return image_id
        except ImageBuildError as e:
            # Re-raise with build logs
            logger.error(f"Image build failed: {e}")
            raise ImageBuildError(f"Image build failed: {e}")
        except Exception as e:
            logger.error(f"Unexpected error during image build: {e}")
            raise ImageBuildError(f"Unexpected error during image build: {e}")
    
    async def _run_container(self, image: str, name: str, env: Dict[str, str], 
                            ports: Dict[int, Optional[int]], 
                            volumes: Optional[Dict[str, Dict[str, str]]] = None) -> str:
        """
        Run a Docker container from an image.
        
        Args:
            image: Image to run
            name: Name for the container
            env: Environment variables
            ports: Port mappings (container_port -> host_port or None for dynamic)
            volumes: Optional volume mappings
            
        Returns:
            ID of the running container
            
        Raises:
            ContainerRunError: If container run fails
        """
        logger.info(f"Running container from image: {image}, name: {name}")
        
        # Handle port mappings
        port_bindings = {}
        for container_port, host_port in ports.items():
            # If host_port is None, Docker will assign a random port
            port_bindings[container_port] = host_port
        
        try:
            # Check if container with this name already exists
            try:
                old_container = self.client.containers.get(name)
                logger.warning(f"Container with name {name} already exists. Removing...")
                
                # Force remove the existing container
                old_container.remove(force=True)
                logger.info(f"Removed existing container: {name}")
            except NotFound:
                # No existing container, which is expected
                pass
            except APIError as e:
                logger.error(f"Error checking for existing container: {e}")
                # Continue anyway
            
            # Run the new container
            container = self.client.containers.run(
                image=image,
                name=name,
                detach=True,  # Run in background
                environment=env,
                ports=port_bindings,
                volumes=volumes,
                remove=True,  # Auto-remove when stopped
            )
            
            # Verify container is running
            container.reload()
            if container.status != 'running':
                raise ContainerRunError(f"Container is not running: {container.status}")
            
            logger.info(f"Container running: {container.id}")
            return container.id
        except ContainerRunError:
            # Re-raise specific error
            raise
        except Exception as e:
            logger.error(f"Error running container: {e}")
            raise ContainerRunError(f"Failed to run container: {e}")
    
    async def _readiness_check(self, url: str, api_key: str, timeout: int = 90) -> bool:
        """
        Check if a deployed server is ready and responding.
        
        Args:
            url: Health check URL
            api_key: API key for authentication
            timeout: Timeout in seconds
            
        Returns:
            True if server is ready, False otherwise
            
        Raises:
            ReadinessCheckError: If readiness check fails after timeout
        """
        import aiohttp
        
        logger.info(f"Performing readiness check for: {url}")
        start_time = time.time()
        
        # Headers for authentication
        headers = {
            "Authorization": f"Bearer {api_key}"
        }
        
        # Create a session for HTTP requests
        async with aiohttp.ClientSession() as session:
            while (time.time() - start_time) < timeout:
                try:
                    # Make a GET request to the health endpoint
                    async with session.get(url, headers=headers, timeout=5) as response:
                        if response.status == 200:
                            logger.info(f"Readiness check succeeded for {url}")
                            return True
                        else:
                            logger.debug(f"Readiness check failed with status {response.status}")
                except aiohttp.ClientConnectorError:
                    logger.debug(f"Connection refused, server not ready yet: {url}")
                except aiohttp.ClientError as e:
                    logger.debug(f"HTTP error during readiness check: {e}")
                except asyncio.TimeoutError:
                    logger.debug(f"Request timeout during readiness check: {url}")
                except Exception as e:
                    logger.debug(f"Unexpected error during readiness check: {e}")
                
                # Wait before retry
                await asyncio.sleep(2)
        
        # Timeout exceeded
        elapsed = time.time() - start_time
        logger.error(f"Readiness check failed after {elapsed:.2f} seconds: {url}")
        raise ReadinessCheckError(f"Server not ready after {timeout} seconds: {url}")
    
    async def build_and_run_utility(self, config: Union[STDIOServerConfig, SSEServerConfig]) -> Dict[str, Any]:
        """
        Build and run a utility server container.
        
        Args:
            config: Configuration for the utility server
            
        Returns:
            Dictionary with deployment details, including the plaintext API key
            
        Raises:
            ImageBuildError: If image build fails
            ContainerRunError: If container run fails
            ReadinessCheckError: If readiness check fails
        """
        logger.info(f"Building and running utility server: {config.name}")
        
        api_key = self._generate_api_key()
        temp_dir = None
        
        try:
            # Create temporary build context directory
            temp_dir = tempfile.mkdtemp(prefix="mcp_cloud_utility_")
            logger.debug(f"Created temporary build context: {temp_dir}")
            
            # Determine template and container params based on transport type
            is_stdio = hasattr(config, 'adapter_port')
            
            if is_stdio:
                internal_port = config.adapter_port
                dockerfile_template = "Dockerfile.stdio_utility.template"
                # Create appropriate dockerfile and copy needed files
                self.template_manager.copy_scaffold_to_context(temp_dir, "stdio")
                server_port = None
            else:
                internal_port = config.server_port
                dockerfile_template = "Dockerfile.sse_utility.template"
                # Create appropriate dockerfile and copy needed files
                self.template_manager.copy_scaffold_to_context(temp_dir, "sse")
                server_port = config.server_port
            
            # Render dockerfile template
            template_params = {
                "command": config.command,
                "port": internal_port
            }
            
            # Write Dockerfile
            dockerfile_path = os.path.join(temp_dir, "Dockerfile")
            with open(dockerfile_path, "w") as f:
                f.write(self._render_dockerfile(dockerfile_template, template_params))
            
            # Generate image tag
            image_tag = f"mcp-utility-{config.name}:{int(time.time())}"
            
            # Build image
            image_id = await self._build_image(temp_dir, image_tag)
            
            # Set up environment variables for the container
            env_vars = {
                "LOG_LEVEL": os.environ.get("LOG_LEVEL", "DEBUG"),
                "MCP_SERVER_API_KEY": api_key,
            }
            
            if is_stdio:
                env_vars.update({
                    "TRANSPORT_TYPE": "stdio",
                    "SERVER_COMMAND": str(config.command),
                    "PORT": str(internal_port)
                })
            else:
                env_vars.update({
                    "TRANSPORT_TYPE": "sse",
                    "SERVER_COMMAND": str(config.command),
                    "PORT": str(internal_port)
                })
            
            # Set up port mapping
            ports = {internal_port: None}  # None means Docker will assign a random host port
            
            # Run container
            container_name = f"mcp-utility-{config.name}-{int(time.time())}"
            container_id = await self._run_container(
                image=image_tag,
                name=container_name,
                env=env_vars,
                ports=ports
            )
            
            # Get container details to find the assigned host port
            container = self.client.containers.get(container_id)
            container.reload()  # Ensure we have the latest info
            
            # Extract host port from container
            port_bindings = container.attrs['NetworkSettings']['Ports']
            key = f"{internal_port}/tcp"
            
            if key not in port_bindings or not port_bindings[key]:
                raise ContainerRunError(f"No port binding found for {key}")
            
            host_port = int(port_bindings[key][0]['HostPort'])
            
            # Construct URLs
            base_url = f"http://localhost:{host_port}"
            health_url = f"{base_url}/health"
            mcp_url = f"{base_url}/mcp"
            
            # Perform readiness check
            await self._readiness_check(health_url, api_key)
            
            # Return deployment details
            result = {
                "container_id": container_id,
                "image_id": image_id,
                "host_port": host_port,
                "url": mcp_url,
                "api_key": api_key  # Return the plaintext key
            }
            
            logger.info(f"Utility server deployed successfully: {config.name}")
            return result
        except Exception as e:
            logger.error(f"Failed to build and run utility server: {e}")
            
            # Try to clean up on failure
            try:
                if temp_dir:
                    os.system(f"rm -rf {temp_dir}")
            except Exception as cleanup_err:
                logger.error(f"Failed to clean up temporary directory: {cleanup_err}")
            
            # Re-raise the original exception
            raise
    
    async def build_and_run_app(self, config: AgentAppServerConfig) -> Dict[str, Any]:
        """
        Build and run an Agent App as MCP Server container.
        
        Args:
            config: Configuration for the Agent App
            
        Returns:
            Dictionary with deployment details, including the plaintext API key
            
        Raises:
            ImageBuildError: If image build fails
            ContainerRunError: If container run fails
            ReadinessCheckError: If readiness check fails
        """
        logger.info(f"Building and running Agent App: {config.name}")
        
        if not config.source_path:
            raise ValueError("Source path is required for Agent App deployment")
        
        if not self.mcp_agent_src_path:
            raise ValueError("Failed to locate mcp-agent source path for local installation")
        
        api_key = self._generate_api_key()
        temp_dir = None
        
        try:
            # Create temporary build context directory
            temp_dir = tempfile.mkdtemp(prefix="mcp_cloud_app_")
            logger.debug(f"Created temporary build context: {temp_dir}")
            
            # Set up build context
            # 1. Create app directory for the application code
            app_dir = os.path.join(temp_dir, "app")
            os.makedirs(app_dir, exist_ok=True)
            
            # 2. Copy application code
            os.system(f"cp -r {config.source_path}/* {app_dir}/")
            
            # 3. Copy mcp-agent source for local installation
            mcp_agent_src_dir = os.path.join(temp_dir, "mcp_agent_src")
            os.makedirs(mcp_agent_src_dir, exist_ok=True)
            os.system(f"cp -r {self.mcp_agent_src_path}/* {mcp_agent_src_dir}/")
            
            # 4. Copy agent app runner script
            self.template_manager.copy_scaffold_to_context(temp_dir, "agent_app")
            
            # Render dockerfile template
            template_params = {
                "app_port": config.app_port,
                "entrypoint": config.entrypoint
            }
            
            # Write Dockerfile
            dockerfile_path = os.path.join(temp_dir, "Dockerfile")
            with open(dockerfile_path, "w") as f:
                f.write(self._render_dockerfile("Dockerfile.agent_app.template", template_params))
            
            # Generate image tag
            image_tag = f"mcp-app-{config.name}:{int(time.time())}"
            
            # Build image
            image_id = await self._build_image(temp_dir, image_tag)
            
            # Set up environment variables for the container
            env_vars = {
                "LOG_LEVEL": os.environ.get("LOG_LEVEL", "DEBUG"),
                "MCP_SERVER_API_KEY": api_key,
                "ENTRYPOINT": config.entrypoint,
                "PORT": str(config.app_port),
                "HTTP_PATH_PREFIX": config.http_path_prefix
            }
            
            # Add all dependencies as environment variables
            env_vars.update(config.dependencies)
            
            # Set up port mapping
            ports = {config.app_port: None}  # None means Docker will assign a random host port
            
            # Run container
            container_name = f"mcp-app-{config.name}-{int(time.time())}"
            container_id = await self._run_container(
                image=image_tag,
                name=container_name,
                env=env_vars,
                ports=ports
            )
            
            # Get container details to find the assigned host port
            container = self.client.containers.get(container_id)
            container.reload()  # Ensure we have the latest info
            
            # Extract host port from container
            port_bindings = container.attrs['NetworkSettings']['Ports']
            key = f"{config.app_port}/tcp"
            
            if key not in port_bindings or not port_bindings[key]:
                raise ContainerRunError(f"No port binding found for {key}")
            
            host_port = int(port_bindings[key][0]['HostPort'])
            
            # Construct URLs
            base_url = f"http://localhost:{host_port}"
            health_url = f"{base_url}/health"
            mcp_url = f"{base_url}{config.http_path_prefix}"
            
            # Perform readiness check
            await self._readiness_check(health_url, api_key)
            
            # Return deployment details
            result = {
                "container_id": container_id,
                "image_id": image_id,
                "host_port": host_port,
                "url": base_url,  # Base URL, not including the MCP prefix
                "api_key": api_key  # Return the plaintext key
            }
            
            logger.info(f"Agent App deployed successfully: {config.name}")
            return result
        except Exception as e:
            logger.error(f"Failed to build and run Agent App: {e}")
            
            # Try to clean up on failure
            try:
                if temp_dir:
                    os.system(f"rm -rf {temp_dir}")
            except Exception as cleanup_err:
                logger.error(f"Failed to clean up temporary directory: {cleanup_err}")
            
            # Re-raise the original exception
            raise
    
    async def stop_and_remove(self, container_id: str) -> bool:
        """
        Stop and remove a container.
        
        Args:
            container_id: ID of the container to stop
            
        Returns:
            True if container was stopped and removed, False otherwise
            
        Raises:
            ContainerError: If container operation fails
        """
        logger.info(f"Stopping and removing container: {container_id}")
        
        try:
            # Get container
            container = self.client.containers.get(container_id)
            
            # Stop container with a timeout
            container.stop(timeout=10)
            
            # No need to remove if we use remove=True when running
            logger.info(f"Container stopped and will be auto-removed: {container_id}")
            
            return True
        except NotFound:
            logger.warning(f"Container not found: {container_id}")
            return False
        except APIError as e:
            logger.error(f"Docker API error: {e}")
            raise ContainerError(f"Failed to stop container: {e}")
        except Exception as e:
            logger.error(f"Unexpected error: {e}")
            raise ContainerError(f"Unexpected error stopping container: {e}")
    
    async def get_logs(self, container_id: str, tail: Optional[int] = 100) -> str:
        """
        Get logs from a container.
        
        Args:
            container_id: ID of the container
            tail: Number of lines to fetch from the end, or None for all logs
            
        Returns:
            Container logs as a string
            
        Raises:
            ContainerError: If logs cannot be retrieved
        """
        logger.debug(f"Getting logs for container: {container_id}")
        
        try:
            # Get container
            container = self.client.containers.get(container_id)
            
            # Get logs
            logs = container.logs(
                stdout=True,
                stderr=True,
                tail=tail,
                timestamps=True
            )
            
            # Convert bytes to string
            logs_str = logs.decode('utf-8', errors='replace')
            return logs_str
        except NotFound:
            logger.warning(f"Container not found: {container_id}")
            raise ContainerError(f"Container not found: {container_id}")
        except APIError as e:
            logger.error(f"Docker API error: {e}")
            raise ContainerError(f"Failed to get logs: {e}")
        except Exception as e:
            logger.error(f"Unexpected error: {e}")
            raise ContainerError(f"Unexpected error getting logs: {e}")
    
    async def get_status(self, container_id: str) -> Dict[str, Any]:
        """
        Get status of a container.
        
        Args:
            container_id: ID of the container
            
        Returns:
            Dictionary with container status information
            
        Raises:
            ContainerError: If status cannot be retrieved
        """
        logger.debug(f"Getting status for container: {container_id}")
        
        try:
            # Get container
            container = self.client.containers.get(container_id)
            
            # Refresh container state
            container.reload()
            
            # Return status
            return {
                "id": container.id,
                "name": container.name,
                "status": container.status,
                "created": container.attrs.get("Created"),
                "started_at": container.attrs.get("State", {}).get("StartedAt"),
                "image": container.image.id,
                "ports": container.attrs.get("NetworkSettings", {}).get("Ports", {})
            }
        except NotFound:
            logger.warning(f"Container not found: {container_id}")
            raise ContainerError(f"Container not found: {container_id}")
        except APIError as e:
            logger.error(f"Docker API error: {e}")
            raise ContainerError(f"Failed to get status: {e}")
        except Exception as e:
            logger.error(f"Unexpected error: {e}")
            raise ContainerError(f"Unexpected error getting status: {e}")