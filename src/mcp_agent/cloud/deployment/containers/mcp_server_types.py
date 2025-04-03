"""
Core model definitions for MCP Agent Cloud deployments.

This module defines the Pydantic models used to represent and validate
different types of MCP Server deployments, including utility servers
(STDIO or SSE based) and Agent Apps that are deployed as MCP Servers.
"""

from datetime import datetime, timezone
from enum import Enum
from typing import Dict, List, Optional, Union, Any, Literal

from pydantic import BaseModel, Field, ConfigDict, field_validator


class DeploymentStatus(str, Enum):
    """Status values for a deployment throughout its lifecycle."""
    PACKAGING = "packaging"  # Only for App deployments during initial packaging
    BUILDING = "building"    # During Docker image build
    RUNNING = "running"      # Container running and ready
    ERROR = "error"          # Error state (build, run, or readiness check failed)
    STOPPED = "stopped"      # Container stopped but not removed


class DeploymentType(str, Enum):
    """Types of deployments supported by the MCP Cloud API."""
    UTILITY = "utility"      # Simple MCP server providing utility functions
    APP = "app"              # Full MCP Agent application deployed as MCP Server


class TransportType(str, Enum):
    """Communication transport types for utility servers."""
    STDIO = "stdio"          # Standard I/O (requires adapter)
    SSE = "sse"              # Server-Sent Events (native HTTP)


class BaseServerConfig(BaseModel):
    """Base configuration shared by all server types."""
    name: str = Field(..., description="The name of the deployment")
    description: str = Field("", description="Optional description of the deployment")
    deployment_type: DeploymentType = Field(
        ..., description="Type of deployment (utility or app)"
    )
    

class STDIOServerConfig(BaseServerConfig):
    """Configuration for a STDIO-based utility server."""
    model_config = ConfigDict(populate_by_name=True)
    
    deployment_type: Literal[DeploymentType.UTILITY] = Field(DeploymentType.UTILITY)
    transport: Literal[TransportType.STDIO] = Field(TransportType.STDIO)
    command: List[str] = Field(
        ..., description="Command to run the STDIO server (e.g. ['python', 'server.py'])"
    )
    adapter_port: int = Field(
        ..., 
        description="Port the adapter will listen on inside the container",
        alias="internal_port"
    )
    
    @field_validator('adapter_port')
    @classmethod
    def validate_port(cls, v: int) -> int:
        """Validate port number is in valid range."""
        if v < 1 or v > 65535:
            raise ValueError("Port must be between 1 and 65535")
        return v


class SSEServerConfig(BaseServerConfig):
    """Configuration for an SSE/HTTP-based utility server."""
    model_config = ConfigDict(populate_by_name=True)
    
    deployment_type: Literal[DeploymentType.UTILITY] = Field(DeploymentType.UTILITY)
    transport: Literal[TransportType.SSE] = Field(TransportType.SSE)
    command: List[str] = Field(
        ..., description="Command to run the SSE server (e.g. ['python', 'server.py'])"
    )
    server_port: int = Field(
        ..., 
        description="Port the server will listen on inside the container",
        alias="internal_port"
    )
    
    @field_validator('server_port')
    @classmethod
    def validate_port(cls, v: int) -> int:
        """Validate port number is in valid range."""
        if v < 1 or v > 65535:
            raise ValueError("Port must be between 1 and 65535")
        return v


class AgentAppServerConfig(BaseServerConfig):
    """Configuration for an Agent App deployed as MCP Server."""
    model_config = ConfigDict(populate_by_name=True)
    
    deployment_type: Literal[DeploymentType.APP] = Field(DeploymentType.APP)
    entrypoint: str = Field(
        ..., description="Python module:variable entrypoint (e.g. 'main:app')"
    )
    app_port: int = Field(
        ..., 
        description="Port the app server will listen on inside the container",
        alias="internal_port"
    )
    http_path_prefix: str = Field(
        "/mcp", description="URL path prefix for MCP Server endpoints"
    )
    dependencies: Dict[str, str] = Field(
        default_factory=dict,
        description="Environment variables to be set in the container (e.g. URLs and API keys for utility servers)"
    )
    source_path: Optional[str] = Field(
        None, description="Path to the source code (set internally during deployment)"
    )
    
    @field_validator('app_port')
    @classmethod
    def validate_port(cls, v: int) -> int:
        """Validate port number is in valid range."""
        if v < 1 or v > 65535:
            raise ValueError("Port must be between 1 and 65535")
        return v
    
    @field_validator('entrypoint')
    @classmethod
    def validate_entrypoint(cls, v: str) -> str:
        """Validate entrypoint is in the format 'module:variable'."""
        if ':' not in v:
            raise ValueError("Entrypoint must be in the format 'module:variable'")
        return v


class ServerDeploymentRecord(BaseModel):
    """Full deployment record stored in the registry."""
    id: str = Field(..., description="Unique identifier for the deployment")
    name: str = Field(..., description="User-provided name of the deployment")
    description: str = Field("", description="Optional description")
    deployment_type: DeploymentType = Field(..., description="Type of deployment")
    status: DeploymentStatus = Field(..., description="Current status of deployment")
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="UTC timestamp when deployment was created"
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="UTC timestamp when deployment was last updated"
    )
    config: Union[STDIOServerConfig, SSEServerConfig, AgentAppServerConfig] = Field(
        ..., description="Server configuration"
    )
    api_key: str = Field(..., description="Hashed API key for server access")
    container_id: Optional[str] = Field(
        None, description="Docker container ID when running"
    )
    image_id: Optional[str] = Field(
        None, description="Docker image ID"
    )
    host_port: Optional[int] = Field(
        None, description="Host port mapped to container"
    )
    url: Optional[str] = Field(
        None, description="URL to access the deployed server"
    )
    error: Optional[str] = Field(
        None, description="Error details if deployment failed"
    )


# Input models for API endpoints

class STDIOServerConfigInput(BaseModel):
    """Input model for creating a STDIO utility server."""
    name: str
    description: str = ""
    command: List[str]
    adapter_port: int


class SSEServerConfigInput(BaseModel):
    """Input model for creating an SSE utility server."""
    name: str
    description: str = ""
    command: List[str]
    server_port: int


class AgentAppServerConfigInput(BaseModel):
    """Input model for creating an Agent App deployment."""
    name: str
    description: str = ""
    entrypoint: str
    app_port: int
    http_path_prefix: str = "/mcp"
    dependencies: Dict[str, str] = Field(default_factory=dict)


# Response models for API endpoints

class DeploymentSummary(BaseModel):
    """Summary of a deployment for list responses."""
    id: str
    name: str
    description: str
    deployment_type: DeploymentType
    status: DeploymentStatus
    created_at: datetime
    updated_at: datetime
    url: Optional[str] = None
    error: Optional[str] = None


class DeploymentResponse(DeploymentSummary):
    """Full deployment details for get/create responses."""
    config: Dict[str, Any]  # Simplified for API responses
    api_key: Optional[str] = None  # Only included in create response