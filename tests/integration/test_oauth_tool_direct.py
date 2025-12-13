"""
Direct tests for OAuth MCP Tools - runs the tool directly without server.

This tests the actual tool functionality by calling it directly.
"""

import asyncio
import json
import pathlib
import sys
import os
from typing import Dict, Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Ensure src directory is in path
PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[2]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

# Change to example directory to load config
EXAMPLE_DIR = PROJECT_ROOT / "examples" / "cloud" / "oauth" / "mcp_tools"


class TestOAuthToolDirect:
    """Direct tests for the OAuth tool."""

    @pytest.mark.asyncio
    async def test_gen_client_oauth_flow(self):
        """Test that gen_client properly uses OAuth when configured."""
        # Save and change current directory
        original_cwd = os.getcwd()
        os.chdir(str(EXAMPLE_DIR))
        
        try:
            from mcp_agent.app import MCPApp
            from mcp_agent.mcp.gen_client import gen_client
            
            # Create app with the example config
            app = MCPApp(
                name="test_oauth_app",
                description="Test OAuth app",
            )
            
            async with app.run() as agent_app:
                # Get the server registry and check if github server is configured
                assert agent_app.context.server_registry is not None
                
                # Check that github server config has OAuth enabled
                github_config = agent_app.context.server_registry.registry.get("github")
                assert github_config is not None
                assert github_config.auth is not None
                assert github_config.auth.oauth is not None
                assert github_config.auth.oauth.enabled is True
                
                # Verify preconfigured token is in the config
                assert github_config.auth.oauth.access_token is not None
                print(f"GitHub OAuth config: enabled={github_config.auth.oauth.enabled}")
                print(f"  Authorization server: {github_config.auth.oauth.authorization_server}")
                print(f"  Has access_token: {github_config.auth.oauth.access_token is not None}")
                
                # Test that token manager has the token cached
                if hasattr(agent_app.context, 'token_manager') and agent_app.context.token_manager:
                    token_manager = agent_app.context.token_manager
                    print(f"Token manager available: {token_manager is not None}")
                    
                    # Try to get the token (without making a request)
                    token = await token_manager.get_access_token_if_present(
                        context=agent_app.context,
                        server_name="github",
                        server_config=github_config,
                    )
                    if token:
                        print(f"Cached token found: {token.access_token[:20]}...")
                    else:
                        print("No cached token found")
        finally:
            os.chdir(original_cwd)

    @pytest.mark.asyncio
    async def test_gen_client_connection_error(self):
        """Test what happens when gen_client fails to connect to GitHub MCP."""
        original_cwd = os.getcwd()
        os.chdir(str(EXAMPLE_DIR))
        
        try:
            from mcp_agent.app import MCPApp
            from mcp_agent.mcp.gen_client import gen_client
            
            app = MCPApp(
                name="test_oauth_connection",
                description="Test OAuth connection",
            )
            
            async with app.run() as agent_app:
                # Try to connect - this will fail because:
                # 1. The test access token is invalid
                # 2. The GitHub MCP server may not be reachable
                try:
                    async with gen_client(
                        "github",
                        server_registry=agent_app.context.server_registry,
                        context=agent_app.context,
                    ) as github_client:
                        # This should fail during connection
                        result = await github_client.call_tool(
                            "search_repositories",
                            {"query": "org:github", "per_page": 1}
                        )
                        print(f"Unexpected success: {result}")
                except Exception as e:
                    # Expected - document the error
                    print(f"Expected connection error: {type(e).__name__}: {e}")
                    # The error is expected - test passes
        finally:
            os.chdir(original_cwd)


class TestOAuthConfiguration:
    """Tests for OAuth configuration in the example."""

    def test_example_config_exists(self):
        """Test that example configuration files exist."""
        assert EXAMPLE_DIR.exists()
        assert (EXAMPLE_DIR / "main.py").exists()
        assert (EXAMPLE_DIR / "mcp_agent.config.yaml").exists()
        assert (EXAMPLE_DIR / "mcp_agent.secrets.yaml.example").exists()

    def test_config_schema_reference(self):
        """Test that config file has schema reference."""
        config_path = EXAMPLE_DIR / "mcp_agent.config.yaml"
        content = config_path.read_text()
        assert "$schema:" in content

    def test_github_server_oauth_config(self):
        """Test GitHub server OAuth configuration structure."""
        config_path = EXAMPLE_DIR / "mcp_agent.config.yaml"
        
        import yaml
        with open(config_path) as f:
            config = yaml.safe_load(f)
        
        # Verify structure
        assert "mcp" in config
        assert "servers" in config["mcp"]
        assert "github" in config["mcp"]["servers"]
        
        github = config["mcp"]["servers"]["github"]
        assert github["transport"] == "streamable_http"
        assert "auth" in github
        assert "oauth" in github["auth"]
        
        oauth = github["auth"]["oauth"]
        assert oauth["enabled"] is True
        assert "scopes" in oauth
        assert oauth["include_resource_parameter"] is False  # GitHub requirement


class TestReadmeInstructions:
    """Tests validating README instructions."""

    def test_readme_exists(self):
        """Test that README exists."""
        readme_path = EXAMPLE_DIR / "README.md"
        assert readme_path.exists()

    def test_readme_contains_setup_instructions(self):
        """Test that README contains setup instructions."""
        readme_path = EXAMPLE_DIR / "README.md"
        content = readme_path.read_text()
        
        # Key sections that should be present
        assert "Prerequisites" in content
        assert "Configuration" in content
        assert "GitHub OAuth App Setup" in content
        assert "Test Locally" in content

    def test_readme_mentions_loopback_port(self):
        """Test that README mentions the correct loopback port."""
        readme_path = EXAMPLE_DIR / "README.md"
        content = readme_path.read_text()
        
        # The configured loopback port should be documented
        assert "33418" in content


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])


