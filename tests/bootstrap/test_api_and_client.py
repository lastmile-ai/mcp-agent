"""Tests for bootstrap API handler and GithubMCPClient.
Follows best practices:
- Arrange-Act-Assert pattern
- Descriptive test names
- Isolated test cases
- Mock external dependencies
- Test edge cases and error paths
"""
import pytest
from unittest.mock import Mock, patch
from starlette.requests import Request
from starlette.responses import JSONResponse
import httpx

from mcp_agent.api.routes.bootstrap_repo import bootstrap_repo_handler
from mcp_agent.services.github_mcp_client import GithubMCPClient


class TestBootstrapRepoHandler:
    """Test suite for bootstrap_repo_handler API endpoint."""

    @pytest.mark.asyncio
    async def test_handler_success_response(self, monkeypatch):
        """Test successful request returns 200 with expected structure."""
        # Arrange
        mock_request = Mock(spec=Request)
        mock_request.json = Mock(return_value={
            "owner": "test-owner",
            "repo": "test-repo",
            "trace_id": "trace-123",
            "language": "python",
            "dry_run": False
        })
        
        mock_result = {"skipped": False, "pr_id": "42", "branch": "vibe/bootstrap"}
        with patch("mcp_agent.api.routes.bootstrap_repo.bootstrap_repo.run", return_value=mock_result):
            # Act
            response = await bootstrap_repo_handler(mock_request)
        
        # Assert
        assert isinstance(response, JSONResponse)
        assert response.status_code == 200
        assert response.body.decode() == '{"skipped":false,"pr_id":"42","branch":"vibe/bootstrap"}'

    @pytest.mark.asyncio
    async def test_handler_missing_owner(self):
        """Test request without owner returns 400 error."""
        # Arrange
        mock_request = Mock(spec=Request)
        mock_request.json = Mock(return_value={"repo": "test-repo"})
        
        # Act
        response = await bootstrap_repo_handler(mock_request)
        
        # Assert
        assert response.status_code == 400
        assert b"owner and repo required" in response.body

    @pytest.mark.asyncio
    async def test_handler_missing_repo(self):
        """Test request without repo returns 400 error."""
        # Arrange
        mock_request = Mock(spec=Request)
        mock_request.json = Mock(return_value={"owner": "test-owner"})
        
        # Act
        response = await bootstrap_repo_handler(mock_request)
        
        # Assert
        assert response.status_code == 400
        assert b"owner and repo required" in response.body

    @pytest.mark.asyncio
    async def test_handler_default_parameters(self):
        """Test handler uses sensible defaults for optional parameters."""
        # Arrange
        mock_request = Mock(spec=Request)
        mock_request.json = Mock(return_value={
            "owner": "test-owner",
            "repo": "test-repo"
        })
        
        mock_run = Mock(return_value={"skipped": True})
        with patch("mcp_agent.api.routes.bootstrap_repo.bootstrap_repo.run", mock_run):
            # Act
            await bootstrap_repo_handler(mock_request)
        
        # Assert
        mock_run.assert_called_once_with(
            owner="test-owner",
            repo="test-repo",
            trace_id="",
            language="auto",
            dry_run=False
        )

    @pytest.mark.asyncio
    async def test_handler_dry_run_flag(self):
        """Test dry_run parameter is correctly passed through."""
        # Arrange
        mock_request = Mock(spec=Request)
        mock_request.json = Mock(return_value={
            "owner": "test-owner",
            "repo": "test-repo",
            "dry_run": True
        })
        
        mock_run = Mock(return_value={"skipped": False, "plan": {}})
        with patch("mcp_agent.api.routes.bootstrap_repo.bootstrap_repo.run", mock_run):
            # Act
            await bootstrap_repo_handler(mock_request)
        
        # Assert
        assert mock_run.call_args.kwargs["dry_run"] is True


class TestGithubMCPClient:
    """Test suite for GithubMCPClient service class."""

    def test_client_initialization_defaults(self):
        """Test client initializes with environment defaults."""
        # Act
        client = GithubMCPClient()
        
        # Assert
        assert client.base_url == ""
        assert client.token == ""
        assert client.timeout == 30.0

    def test_client_initialization_custom_values(self):
        """Test client accepts custom configuration."""
        # Act
        client = GithubMCPClient(
            base_url="https://api.example.com",
            token="test-token",
            timeout=60.0
        )
        
        # Assert
        assert client.base_url == "https://api.example.com"
        assert client.token == "test-token"
        assert client.timeout == 60.0

    def test_headers_without_token(self):
        """Test _headers returns basic headers when no token provided."""
        # Arrange
        client = GithubMCPClient()
        
        # Act
        headers = client._headers()
        
        # Assert
        assert headers == {"Content-Type": "application/json"}

    def test_headers_with_token(self):
        """Test _headers includes Bearer auth when token provided."""
        # Arrange
        client = GithubMCPClient(token="secret-token")
        
        # Act
        headers = client._headers()
        
        # Assert
        assert headers["Authorization"] == "Bearer secret-token"
        assert headers["Content-Type"] == "application/json"

    def test_get_default_branch_success(self):
        """Test get_default_branch returns branch name on success."""
        # Arrange
        client = GithubMCPClient(base_url="https://api.test.com")
        mock_response = Mock()
        mock_response.json.return_value = {"default_branch": "develop"}
        
        with patch("httpx.get", return_value=mock_response) as mock_get:
            # Act
            result = client.get_default_branch("owner", "repo")
        
        # Assert
        assert result == "develop"
        mock_get.assert_called_once()

    def test_get_default_branch_fallback(self):
        """Test get_default_branch returns 'main' when API returns None."""
        # Arrange
        client = GithubMCPClient(base_url="https://api.test.com")
        mock_response = Mock()
        mock_response.json.return_value = {"default_branch": None}
        
        with patch("httpx.get", return_value=mock_response):
            # Act
            result = client.get_default_branch("owner", "repo")
        
        # Assert
        assert result == "main"

    def test_stat_file_exists(self):
        """Test stat returns True when file exists (200 response)."""
        # Arrange
        client = GithubMCPClient(base_url="https://api.test.com")
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.raise_for_status = Mock()
        
        with patch("httpx.get", return_value=mock_response):
            # Act
            result = client.stat("owner", "repo", "main", "README.md")
        
        # Assert
        assert result is True

    def test_stat_file_not_found(self):
        """Test stat returns False for 404 response."""
        # Arrange
        client = GithubMCPClient(base_url="https://api.test.com")
        mock_response = Mock()
        mock_response.status_code = 404
        
        with patch("httpx.get", return_value=mock_response):
            # Act
            result = client.stat("owner", "repo", "main", "missing.txt")
        
        # Assert
        assert result is False

    def test_stat_server_error_raises(self):
        """Test stat raises exception for 5xx errors."""
        # Arrange
        client = GithubMCPClient(base_url="https://api.test.com")
        mock_response = Mock()
        mock_response.status_code = 500
        mock_response.raise_for_status = Mock(side_effect=httpx.HTTPStatusError(
            "Server Error", request=Mock(), response=mock_response
        ))
        
        with patch("httpx.get", return_value=mock_response):
            # Act & Assert
            with pytest.raises(httpx.HTTPStatusError):
                client.stat("owner", "repo", "main", "file.txt")

    def test_create_branch_success(self):
        """Test create_branch makes correct API call."""
        # Arrange
        client = GithubMCPClient(base_url="https://api.test.com", token="test-token")
        mock_response = Mock()
        mock_response.raise_for_status = Mock()
        
        with patch("httpx.post", return_value=mock_response) as mock_post:
            # Act
            client.create_branch("owner", "repo", "main", "feature/test")
        
        # Assert
        mock_post.assert_called_once()
        call_args = mock_post.call_args
        assert call_args.kwargs["json"] == {
            "owner": "owner",
            "repo": "repo",
            "base": "main",
            "name": "feature/test"
        }

    def test_put_add_only_creates_file(self):
        """Test put_add_only successfully creates a new file."""
        # Arrange
        client = GithubMCPClient(base_url="https://api.test.com")
        mock_response = Mock()
        mock_response.raise_for_status = Mock()
        mock_response.content = b'{"created": true, "message": "created"}'
        mock_response.json.return_value = {"created": True, "message": "created"}
        
        with patch("httpx.put", return_value=mock_response):
            # Act
            created, message = client.put_add_only(
                "owner", "repo", "main", "test.txt", b"content"
            )
        
        # Assert
        assert created is True
        assert message == "created"

    def test_open_pr_returns_id(self):
        """Test open_pr returns pull request ID."""
        # Arrange
        client = GithubMCPClient(base_url="https://api.test.com")
        mock_response = Mock()
        mock_response.raise_for_status = Mock()
        mock_response.json.return_value = {"id": "123"}
        
        with patch("httpx.post", return_value=mock_response):
            # Act
            pr_id = client.open_pr(
                "owner", "repo", "main", "feature", "Title", "Body"
            )
        
        # Assert
        assert pr_id == "123"

    def test_run_ci_on_pr_success(self):
        """Test run_ci_on_pr makes correct API call."""
        # Arrange
        client = GithubMCPClient(base_url="https://api.test.com")
        mock_response = Mock()
        mock_response.raise_for_status = Mock()
        
        with patch("httpx.post", return_value=mock_response) as mock_post:
            # Act
            client.run_ci_on_pr("owner", "repo", "123")
        
        # Assert
        mock_post.assert_called_once()
        assert mock_post.call_args.kwargs["json"]["pr_id"] == "123"
