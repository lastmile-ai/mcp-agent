"""Utilities for Vault integration testing.

This module provides functions and fixtures for setting up and managing
a Vault instance for integration tests. It supports both local Docker-based
Vault instances and remote Vault instances.
"""

import os
import json
import uuid
import time
import subprocess
import shutil
from pathlib import Path
from enum import Enum
from typing import Optional, Tuple, Dict, Any

import requests


class VaultMode(str, Enum):
    """Enum for Vault test modes."""
    
    LOCAL = "local"       # Use a local Docker Vault instance
    REMOTE = "remote"     # Use a remote Vault instance
    AUTO = "auto"         # Detect automatically based on environment variables


class VaultTestManager:
    """Manager for Vault integration testing.
    
    This class handles the lifecycle of a Vault instance for testing,
    including setup, health checks, and teardown.
    """
    
    VAULT_ADDR_ENV = "VAULT_ADDR"
    VAULT_TOKEN_ENV = "VAULT_TOKEN"
    MCP_VAULT_MODE_ENV = "MCP_VAULT_MODE"
    
    DEFAULT_LOCAL_ADDR = "http://localhost:8200"
    DEFAULT_LOCAL_TOKEN = "dev-token"
    CONTAINER_NAME = "mcp-vault-test"
    
    def __init__(self, mode: VaultMode = VaultMode.AUTO, force_clean: bool = False):
        """Initialize the Vault test manager.
        
        Args:
            mode: The Vault test mode to use
            force_clean: If True, force cleanup of any existing local Vault container
        """
        self.mode = mode
        self.force_clean = force_clean
        
        # Track whether we created the container (for cleanup)
        self.created_container = False
        
        # Find the vault_test_setup.sh script
        self.base_dir = Path(__file__).resolve().parent.parent.parent
        self.setup_script = self.base_dir / "scripts" / "vault_test_setup.sh"
        
        if not self.setup_script.exists():
            raise FileNotFoundError(
                f"Vault setup script not found at {self.setup_script}"
            )
        
        # Check if Docker is available if mode is LOCAL
        if mode == VaultMode.LOCAL:
            if not shutil.which("docker"):
                raise EnvironmentError("Docker is not installed or not in PATH")
    
    def setup(self) -> Tuple[str, str]:
        """Set up a Vault instance for testing.
        
        This method will:
        1. If mode is REMOTE, verify the connection to the remote Vault
        2. If mode is LOCAL, start a local Docker Vault instance
        3. If mode is AUTO, try REMOTE first, then fall back to LOCAL
        
        Returns:
            Tuple[str, str]: The Vault address and token
        
        Raises:
            RuntimeError: If Vault setup fails
        """
        if self.mode == VaultMode.REMOTE:
            return self._setup_remote()
        elif self.mode == VaultMode.LOCAL:
            return self._setup_local()
        else:  # AUTO
            try:
                return self._setup_remote()
            except RuntimeError:
                print("Remote Vault not available, falling back to local Docker instance")
                return self._setup_local()
    
    def _setup_remote(self) -> Tuple[str, str]:
        """Set up and verify a remote Vault connection.
        
        Returns:
            Tuple[str, str]: The Vault address and token
        
        Raises:
            RuntimeError: If remote Vault setup fails
        """
        vault_addr = os.environ.get(self.VAULT_ADDR_ENV)
        vault_token = os.environ.get(self.VAULT_TOKEN_ENV)
        
        if not vault_addr or not vault_token:
            raise RuntimeError(
                f"Remote Vault mode requires {self.VAULT_ADDR_ENV} and {self.VAULT_TOKEN_ENV} "
                "environment variables to be set"
            )
        
        # Verify connection and token validity
        if not self._verify_vault_connection(vault_addr, vault_token):
            raise RuntimeError(f"Failed to connect to Vault at {vault_addr} or invalid token")
        
        print(f"Successfully connected to remote Vault at {vault_addr}")
        
        # Set environment variables for tests
        os.environ[self.VAULT_ADDR_ENV] = vault_addr
        os.environ[self.VAULT_TOKEN_ENV] = vault_token
        os.environ[self.MCP_VAULT_MODE_ENV] = VaultMode.REMOTE
        
        return vault_addr, vault_token
    
    def _setup_local(self) -> Tuple[str, str]:
        """Set up a local Docker Vault instance.
        
        Returns:
            Tuple[str, str]: The Vault address and token
        
        Raises:
            RuntimeError: If local Vault setup fails
        """
        vault_addr = self.DEFAULT_LOCAL_ADDR
        vault_token = self.DEFAULT_LOCAL_TOKEN
        
        # Check if a Vault container is already running
        container_id = self._get_vault_container_id()
        
        if container_id:
            print(f"Using existing Vault container: {container_id}")
            if self.force_clean:
                print("Forcing cleanup of existing container...")
                self._cleanup_vault_container(container_id)
                container_id = None
        
        # Start a new container if needed
        if not container_id:
            print("Starting new Vault container...")
            container_id = self._start_vault_container()
            if not container_id:
                raise RuntimeError("Failed to start Vault container")
            print(f"Started Vault container: {container_id}")
            self.created_container = True
        
        # Wait for Vault to be ready
        max_retries = 10
        retry_count = 0
        while retry_count < max_retries:
            if self._verify_vault_connection(vault_addr, vault_token):
                break
            print(f"Waiting for Vault to be ready (attempt {retry_count+1}/{max_retries})...")
            time.sleep(2)
            retry_count += 1
        
        if retry_count >= max_retries:
            if self.created_container:
                self._cleanup_vault_container(container_id)
            raise RuntimeError(f"Vault did not become ready after {max_retries} attempts")
        
        # Configure Vault for testing
        if not self._configure_vault_for_testing(vault_addr, vault_token):
            if self.created_container:
                self._cleanup_vault_container(container_id)
            raise RuntimeError("Failed to configure Vault for testing")
        
        # Set environment variables for tests
        os.environ[self.VAULT_ADDR_ENV] = vault_addr
        os.environ[self.VAULT_TOKEN_ENV] = vault_token
        os.environ[self.MCP_VAULT_MODE_ENV] = VaultMode.LOCAL
        
        return vault_addr, vault_token
    
    def cleanup(self) -> None:
        """Clean up Vault resources after testing.
        
        This will only stop and remove the local Docker container if
        it was created by this instance.
        """
        if self.mode == VaultMode.LOCAL or (
            self.mode == VaultMode.AUTO and 
            os.environ.get(self.MCP_VAULT_MODE_ENV) == VaultMode.LOCAL
        ):
            if self.created_container:
                container_id = self._get_vault_container_id()
                if container_id:
                    print(f"Cleaning up Vault container: {container_id}")
                    self._cleanup_vault_container(container_id)
    
    def _verify_vault_connection(self, addr: str, token: str) -> bool:
        """Verify connection to a Vault instance.
        
        Args:
            addr: The Vault address
            token: The Vault token
        
        Returns:
            bool: True if the connection was successful, False otherwise
        """
        try:
            # Check Vault health
            health_response = requests.get(f"{addr}/v1/sys/health", timeout=5)
            if health_response.status_code not in (200, 429, 472, 473, 501, 503):
                print(f"Vault health check failed: {health_response.status_code}")
                return False
            
            # Check token validity
            token_response = requests.get(
                f"{addr}/v1/auth/token/lookup-self",
                headers={"X-Vault-Token": token},
                timeout=5
            )
            if token_response.status_code != 200:
                print(f"Token validation failed: {token_response.status_code}")
                return False
            
            return True
        except Exception as e:
            print(f"Error verifying Vault connection: {e}")
            return False
    
    def _get_vault_container_id(self) -> Optional[str]:
        """Get the ID of the running Vault container.
        
        Returns:
            Optional[str]: The container ID, or None if not running
        """
        try:
            # Use docker ps to check if the container is running
            result = subprocess.run(
                ["docker", "ps", "--filter", f"name={self.CONTAINER_NAME}", "--format", "{{.ID}}"],
                capture_output=True,
                text=True,
                check=False
            )
            
            container_id = result.stdout.strip()
            return container_id if container_id else None
        except Exception as e:
            print(f"Error getting Vault container ID: {e}")
            return None
    
    def _start_vault_container(self) -> Optional[str]:
        """Start a new Vault container.
        
        Returns:
            Optional[str]: The container ID, or None if start failed
        """
        try:
            # Remove any existing container with the same name
            existing_id = subprocess.run(
                ["docker", "ps", "-a", "--filter", f"name={self.CONTAINER_NAME}", "--format", "{{.ID}}"],
                capture_output=True,
                text=True,
                check=False
            ).stdout.strip()
            
            if existing_id:
                subprocess.run(
                    ["docker", "rm", "-f", existing_id],
                    capture_output=True,
                    check=False
                )
            
            # Start a new container
            result = subprocess.run(
                [
                    "docker", "run", "-d",
                    "--cap-add=IPC_LOCK",
                    "-p", "8200:8200",
                    "-e", f"VAULT_DEV_ROOT_TOKEN_ID={self.DEFAULT_LOCAL_TOKEN}",
                    "--name", self.CONTAINER_NAME,
                    "hashicorp/vault:latest"
                ],
                capture_output=True,
                text=True,
                check=False
            )
            
            if result.returncode != 0:
                print(f"Error starting Vault container: {result.stderr}")
                return None
            
            container_id = result.stdout.strip()
            return container_id
        except Exception as e:
            print(f"Error starting Vault container: {e}")
            return None
    
    def _cleanup_vault_container(self, container_id: str) -> bool:
        """Clean up a Vault container.
        
        Args:
            container_id: The container ID
        
        Returns:
            bool: True if cleanup was successful, False otherwise
        """
        try:
            # Stop and remove the container
            subprocess.run(
                ["docker", "stop", container_id],
                capture_output=True,
                check=False
            )
            subprocess.run(
                ["docker", "rm", container_id],
                capture_output=True,
                check=False
            )
            return True
        except Exception as e:
            print(f"Error cleaning up Vault container: {e}")
            return False
    
    def _configure_vault_for_testing(self, addr: str, token: str) -> bool:
        """Configure Vault for testing.
        
        Args:
            addr: The Vault address
            token: The Vault token
        
        Returns:
            bool: True if configuration was successful, False otherwise
        """
        try:
            # Check if KV v2 secrets engine is enabled
            mounts_response = requests.get(
                f"{addr}/v1/sys/mounts",
                headers={"X-Vault-Token": token},
                timeout=5
            )
            
            if mounts_response.status_code != 200:
                print(f"Error checking Vault mounts: {mounts_response.status_code}")
                return False
            
            mounts = mounts_response.json()
            
            # Enable KV v2 secrets engine if needed
            if "secret/" not in mounts:
                kv_response = requests.post(
                    f"{addr}/v1/sys/mounts/secret",
                    headers={
                        "X-Vault-Token": token,
                        "Content-Type": "application/json"
                    },
                    json={"type": "kv", "options": {"version": 2}},
                    timeout=5
                )
                
                if kv_response.status_code != 204:
                    print(f"Error enabling KV secrets engine: {kv_response.status_code}")
                    return False
                
                print("Enabled KV v2 secrets engine")
            
            # Create policy for MCP tests
            policy_content = """
            path "secret/data/mcp/mvp0_secrets/*" {
              capabilities = ["create", "read", "update", "delete", "list"]
            }
            path "secret/metadata/mcp/mvp0_secrets/*" {
              capabilities = ["list"]
            }
            path "secret/metadata/mcp/mvp0_secrets" {
              capabilities = ["list"]
            }
            path "secret/data/mcpac_mvp0_dev_*" {
              capabilities = ["create", "read", "update", "delete", "list"]
            }
            path "secret/data/mcpac_mvp0_usr_*" {
              capabilities = ["create", "read", "update", "delete", "list"]
            }
            path "secret/metadata/mcpac_mvp0_*" {
              capabilities = ["list"]
            }
            """
            
            policy_response = requests.put(
                f"{addr}/v1/sys/policies/acl/mcp-test-policy",
                headers={
                    "X-Vault-Token": token,
                    "Content-Type": "application/json"
                },
                json={"policy": policy_content},
                timeout=5
            )
            
            if policy_response.status_code != 204:
                print(f"Error creating policy: {policy_response.status_code}")
                return False
            
            print("Created policy for MCP tests")
            
            return True
        except Exception as e:
            print(f"Error configuring Vault: {e}")
            return False


def get_vault_manager(mode: VaultMode = VaultMode.AUTO, force_clean: bool = False) -> VaultTestManager:
    """Get a VaultTestManager instance.
    
    Args:
        mode: The Vault test mode to use
        force_clean: If True, force cleanup of any existing local Vault container
    
    Returns:
        VaultTestManager: A VaultTestManager instance
    """
    return VaultTestManager(mode=mode, force_clean=force_clean)


def setup_vault_for_testing(mode: VaultMode = VaultMode.AUTO, force_clean: bool = False) -> Tuple[str, str]:
    """Set up a Vault instance for testing.
    
    Args:
        mode: The Vault test mode to use
        force_clean: If True, force cleanup of any existing local Vault container
    
    Returns:
        Tuple[str, str]: The Vault address and token
    """
    manager = get_vault_manager(mode=mode, force_clean=force_clean)
    return manager.setup()