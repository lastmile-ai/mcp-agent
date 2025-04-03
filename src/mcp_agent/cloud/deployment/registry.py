"""
Registry implementation for managing MCP Server deployments.

This module provides a JSON file-based registry to track and manage all 
deployments, including their configuration, status, and access details.
"""

import asyncio
import copy
import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Any, Union

import bcrypt

from .containers.mcp_server_types import (
    ServerDeploymentRecord,
    DeploymentStatus,
    DeploymentType,
    STDIOServerConfig,
    SSEServerConfig,
    AgentAppServerConfig
)

# Configure logger
logger = logging.getLogger("mcp_cloud.registry")


class JsonServerRegistry:
    """
    Registry for tracking MCP Server deployments using a JSON file.
    
    This registry stores deployment records in a JSON file with atomic updates
    and proper concurrency control using asyncio locks.
    """
    
    def __init__(self, registry_path: Optional[str] = None):
        """
        Initialize the registry with the specified file path.
        
        Args:
            registry_path: Path to the registry JSON file. If None, 
                           defaults to ~/.mcp-agent-cloud/registry.json
        """
        # Default path to ~/.mcp-agent-cloud/registry.json if not provided
        if registry_path is None:
            home_dir = Path.home()
            registry_dir = home_dir / ".mcp-agent-cloud"
            # Create directory if it doesn't exist
            registry_dir.mkdir(exist_ok=True, parents=True)
            self.registry_path = registry_dir / "registry.json"
        else:
            self.registry_path = Path(registry_path)
            # Create parent directory if it doesn't exist
            self.registry_path.parent.mkdir(exist_ok=True, parents=True)
        
        # Create empty registry file if it doesn't exist
        if not self.registry_path.exists():
            self._write_registry_data({})
        
        # Lock for thread safety during registry operations
        self._lock = asyncio.Lock()
        
        logger.info(f"Registry initialized at {self.registry_path}")
    
    def _write_registry_data(self, data: Dict[str, Any]) -> None:
        """
        Write registry data to the JSON file atomically.
        
        Args:
            data: Dictionary containing registry data
        """
        # Write to a temporary file first
        temp_path = f"{self.registry_path}.tmp"
        try:
            with open(temp_path, 'w') as f:
                json.dump(data, f, indent=2, default=str)
            
            # Replace the original file atomically
            os.replace(temp_path, self.registry_path)
        except Exception as e:
            logger.error(f"Failed to write registry data: {e}")
            # Cleanup temp file if it exists
            if os.path.exists(temp_path):
                os.remove(temp_path)
            raise
    
    def _read_registry_data(self) -> Dict[str, Any]:
        """
        Read registry data from the JSON file.
        
        Returns:
            Dictionary containing registry data
        """
        try:
            with open(self.registry_path, 'r') as f:
                data = json.load(f)
                # Ensure we always return a dictionary
                if not isinstance(data, dict):
                    logger.warning(f"Registry data is not a dictionary, got {type(data).__name__}. Creating new registry.")
                    return {}
                return data
        except json.JSONDecodeError as e:
            logger.error(f"Failed to decode registry JSON: {e}")
            # Return empty registry on decode error
            return {}
        except FileNotFoundError:
            logger.warning(f"Registry file not found at {self.registry_path}")
            # Create empty registry file
            self._write_registry_data({})
            return {}
        except Exception as e:
            logger.error(f"Failed to read registry data: {e}")
            raise
    
    def _hash_api_key(self, api_key: str) -> str:
        """
        Hash the API key using bcrypt.
        
        Args:
            api_key: The plaintext API key to hash
            
        Returns:
            Hashed API key string
        """
        # Hash the API key using bcrypt
        hashed = bcrypt.hashpw(api_key.encode('utf-8'), bcrypt.gensalt())
        return hashed.decode('utf-8')
    
    def _verify_api_key(self, hashed_key: str, api_key: str) -> bool:
        """
        Verify if the provided API key matches the hash.
        
        Args:
            hashed_key: The bcrypt hash stored in the registry
            api_key: The plaintext API key to verify
            
        Returns:
            True if the key matches the hash, False otherwise
        """
        return bcrypt.checkpw(api_key.encode('utf-8'), hashed_key.encode('utf-8'))
    
    def _serialize_config(self, config: Union[STDIOServerConfig, SSEServerConfig, AgentAppServerConfig]) -> Dict[str, Any]:
        """
        Serialize a config object to a dictionary for JSON storage.
        
        Args:
            config: The server configuration object
            
        Returns:
            Dictionary representation of the config
        """
        return config.model_dump()
    
    def _deserialize_config(self, config_dict: Dict[str, Any]) -> Union[STDIOServerConfig, SSEServerConfig, AgentAppServerConfig]:
        """
        Deserialize a dictionary to the appropriate config object.
        
        Args:
            config_dict: Dictionary representation of a config
            
        Returns:
            The server configuration object
        """
        deployment_type = config_dict.get('deployment_type')
        
        if deployment_type == DeploymentType.UTILITY:
            transport = config_dict.get('transport')
            if transport == 'stdio':
                return STDIOServerConfig(**config_dict)
            elif transport == 'sse':
                return SSEServerConfig(**config_dict)
            else:
                raise ValueError(f"Unknown transport type: {transport}")
        elif deployment_type == DeploymentType.APP:
            return AgentAppServerConfig(**config_dict)
        else:
            raise ValueError(f"Unknown deployment type: {deployment_type}")
    
    def _deserialize_record(self, record_dict: Dict[str, Any]) -> ServerDeploymentRecord:
        """
        Deserialize a dictionary to a ServerDeploymentRecord.
        
        Args:
            record_dict: Dictionary representation of a record
            
        Returns:
            The ServerDeploymentRecord object
        """
        # Deep copy to avoid modifying the original
        record = copy.deepcopy(record_dict)
        
        # Convert string timestamps to datetime objects
        if isinstance(record.get('created_at'), str):
            record['created_at'] = datetime.fromisoformat(record['created_at'])
        
        if isinstance(record.get('updated_at'), str):
            record['updated_at'] = datetime.fromisoformat(record['updated_at'])
        
        # Convert config dict to appropriate object
        if 'config' in record and isinstance(record['config'], dict):
            record['config'] = self._deserialize_config(record['config'])
        
        return ServerDeploymentRecord(**record)
    
    async def register(self, id: str, name: str, description: str, 
                      config: Union[STDIOServerConfig, SSEServerConfig, AgentAppServerConfig], 
                      api_key: str, status: DeploymentStatus) -> None:
        """
        Register a new deployment in the registry.
        
        Args:
            id: Unique identifier for the deployment
            name: Name of the deployment
            description: Description of the deployment
            config: Server configuration
            api_key: Plaintext API key for server access (will be hashed)
            status: Initial status of the deployment
        """
        logger.info(f"Registering new deployment: {id} - {name}")
        
        # Create record with current timestamp and hashed API key
        now = datetime.now(timezone.utc)
        record = ServerDeploymentRecord(
            id=id,
            name=name,
            description=description,
            deployment_type=config.deployment_type,
            status=status,
            created_at=now,
            updated_at=now,
            config=config,
            api_key=self._hash_api_key(api_key),
            container_id=None,
            image_id=None,
            host_port=None,
            url=None,
            error=None
        )
        
        # Serialize the record
        record_dict = json.loads(json.dumps(record.model_dump(), default=str))
        
        # Use lock to ensure atomic read-modify-write
        async with self._lock:
            registry_data = self._read_registry_data()
            # Check if id already exists
            if id in registry_data:
                raise ValueError(f"Deployment ID already exists: {id}")
            
            # Add new record
            registry_data[id] = record_dict
            self._write_registry_data(registry_data)
        
        logger.debug(f"Registered deployment: {id}")
    
    async def get(self, id: str) -> Optional[ServerDeploymentRecord]:
        """
        Get a deployment record by ID.
        
        Args:
            id: The unique identifier of the deployment
            
        Returns:
            The deployment record or None if not found
        """
        logger.debug(f"Getting deployment: {id}")
        
        async with self._lock:
            registry_data = self._read_registry_data()
            if id not in registry_data:
                logger.warning(f"Deployment not found: {id}")
                return None
            
            return self._deserialize_record(registry_data[id])
    
    async def list_all(self) -> List[ServerDeploymentRecord]:
        """
        List all deployment records.
        
        Returns:
            List of all deployment records
        """
        logger.debug("Listing all deployments")
        
        async with self._lock:
            registry_data = self._read_registry_data()
            return [self._deserialize_record(record) for record in registry_data.values()]
    
    async def update_status(self, id: str, status: DeploymentStatus, 
                           container_id: Optional[str] = None,
                           image_id: Optional[str] = None,
                           host_port: Optional[int] = None,
                           url: Optional[str] = None,
                           error: Optional[str] = None) -> Optional[ServerDeploymentRecord]:
        """
        Update the status and runtime details of a deployment.
        
        Args:
            id: The unique identifier of the deployment
            status: The new status
            container_id: Optional Docker container ID
            image_id: Optional Docker image ID
            host_port: Optional host port mapped to the container
            url: Optional URL to access the deployed server
            error: Optional error message if status is ERROR
            
        Returns:
            The updated deployment record or None if not found
        """
        logger.info(f"Updating deployment {id} status to {status}")
        
        async with self._lock:
            registry_data = self._read_registry_data()
            if id not in registry_data:
                logger.warning(f"Deployment not found: {id}")
                return None
            
            # Get the current record
            record = registry_data[id]
            
            # Update the record
            record['status'] = status
            record['updated_at'] = datetime.now(timezone.utc).isoformat()
            
            # Update optional fields if provided
            if container_id is not None:
                record['container_id'] = container_id
            
            if image_id is not None:
                record['image_id'] = image_id
            
            if host_port is not None:
                record['host_port'] = host_port
            
            if url is not None:
                record['url'] = url
            
            if error is not None:
                record['error'] = error
            
            # Write updated data
            self._write_registry_data(registry_data)
            
            return self._deserialize_record(record)
    
    async def remove(self, id: str) -> bool:
        """
        Remove a deployment from the registry.
        
        Args:
            id: The unique identifier of the deployment
            
        Returns:
            True if the deployment was removed, False if not found
        """
        logger.info(f"Removing deployment: {id}")
        
        async with self._lock:
            registry_data = self._read_registry_data()
            if id not in registry_data:
                logger.warning(f"Deployment not found: {id}")
                return False
            
            # Remove the record
            del registry_data[id]
            self._write_registry_data(registry_data)
            
            return True
    
    async def find_by_name(self, name: str) -> Optional[ServerDeploymentRecord]:
        """
        Find a deployment by name.
        
        Args:
            name: The name of the deployment
            
        Returns:
            The first deployment record with the matching name or None if not found
        """
        logger.debug(f"Finding deployment by name: {name}")
        
        async with self._lock:
            registry_data = self._read_registry_data()
            for record in registry_data.values():
                if record.get('name') == name:
                    return self._deserialize_record(record)
            
            logger.warning(f"Deployment not found with name: {name}")
            return None