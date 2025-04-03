"""
Template manager for Docker container configurations.

This module provides a TemplateManager class that handles rendering Dockerfile
templates and copying scaffold files for different container types.
"""

import logging
import os
import shutil
from pathlib import Path
from typing import Dict, Any, Optional

import jinja2

# Configure logger
logger = logging.getLogger("mcp_cloud.template")


class TemplateManager:
    """
    Manager for templates used in container deployments.
    
    This class handles locating, rendering, and copying templates and scaffold
    files for different container types.
    """
    
    def __init__(self, templates_dir: Optional[str] = None):
        """
        Initialize the template manager.
        
        Args:
            templates_dir: Optional path to templates directory. If None,
                          defaults to the 'templates' directory relative to this file.
        """
        # Find templates directory if not provided
        if templates_dir is None:
            # Get directory of this file
            current_file = Path(__file__)
            # Templates are in ../templates relative to this file
            templates_dir = current_file.parent.parent / "templates"
        
        self.templates_dir = Path(templates_dir)
        logger.info(f"Template manager initialized with templates directory: {self.templates_dir}")
        
        # If templates directory doesn't exist, create it
        if not self.templates_dir.exists():
            self.templates_dir.mkdir(parents=True, exist_ok=True)
            logger.warning(f"Templates directory didn't exist. Created: {self.templates_dir}")
        
        # Initialize Jinja2 environment
        self.jinja_env = jinja2.Environment(
            loader=jinja2.FileSystemLoader(str(self.templates_dir)),
            autoescape=jinja2.select_autoescape(['html', 'xml']),
            trim_blocks=True,
            lstrip_blocks=True
        )
    
    def get_template_path(self, template_name: str) -> Path:
        """
        Get the path to a template file.
        
        Args:
            template_name: Name of the template file
            
        Returns:
            Path to the template file
            
        Raises:
            FileNotFoundError: If the template doesn't exist
        """
        template_path = self.templates_dir / template_name
        if not template_path.exists():
            error_msg = f"Template not found: {template_name}"
            logger.error(error_msg)
            raise FileNotFoundError(error_msg)
        
        return template_path
    
    def _get_dockerfile_template_name(self, container_type: str) -> str:
        """
        Get the appropriate Dockerfile template name for a container type.
        
        Args:
            container_type: Type of container ('stdio', 'sse', or 'agent_app')
            
        Returns:
            Name of the Dockerfile template
            
        Raises:
            ValueError: If the container type is unknown
        """
        if container_type == "stdio":
            return "Dockerfile.stdio_utility.template"
        elif container_type == "sse":
            return "Dockerfile.sse_utility.template"
        elif container_type == "agent_app":
            return "Dockerfile.agent_app.template"
        else:
            error_msg = f"Unknown container type: {container_type}"
            logger.error(error_msg)
            raise ValueError(error_msg)
    
    def render_template(self, template_name: str, context: Dict[str, Any]) -> str:
        """
        Render a template with the given context.
        
        Args:
            template_name: Name of the template file
            context: Dictionary of values to render into the template
            
        Returns:
            Rendered template content
            
        Raises:
            jinja2.exceptions.TemplateError: If template rendering fails
        """
        logger.debug(f"Rendering template: {template_name}")
        
        try:
            template = self.jinja_env.get_template(template_name)
            return template.render(**context)
        except jinja2.exceptions.TemplateError as e:
            error_msg = f"Failed to render template {template_name}: {e}"
            logger.error(error_msg)
            raise
    
    def copy_scaffold_to_context(self, context_path: str, container_type: str) -> None:
        """
        Copy the appropriate scaffold files to a Docker build context.
        
        Args:
            context_path: Path to the Docker build context directory
            container_type: Type of container ('stdio', 'sse', or 'agent_app')
            
        Raises:
            FileNotFoundError: If scaffold files don't exist
            ValueError: If the container type is unknown
        """
        logger.debug(f"Copying scaffold files for {container_type} to {context_path}")
        
        # Make sure the context directory exists
        if not os.path.exists(context_path):
            os.makedirs(context_path, exist_ok=True)
        
        # Copy appropriate files based on container type
        if container_type == "stdio":
            # For STDIO, copy the adapter script and utility runner
            self._copy_file("stdio_adapter.py", context_path)
            self._copy_file("utility_runner.py", context_path)
        elif container_type == "sse":
            # For SSE, just copy the utility runner
            self._copy_file("utility_runner.py", context_path)
        elif container_type == "agent_app":
            # For Agent App, copy the agent app runner
            self._copy_file("agent_app_runner.py", context_path)
        else:
            error_msg = f"Unknown container type: {container_type}"
            logger.error(error_msg)
            raise ValueError(error_msg)
    
    def _copy_file(self, file_name: str, destination: str) -> None:
        """
        Copy a file from the templates directory to the destination.
        
        Args:
            file_name: Name of the file to copy
            destination: Destination directory
            
        Raises:
            FileNotFoundError: If the file doesn't exist
        """
        source_path = self.templates_dir / file_name
        dest_path = Path(destination) / file_name
        
        if not source_path.exists():
            error_msg = f"Template file not found: {source_path}"
            logger.error(error_msg)
            raise FileNotFoundError(error_msg)
        
        shutil.copy2(source_path, dest_path)
        logger.debug(f"Copied {file_name} to {dest_path}")