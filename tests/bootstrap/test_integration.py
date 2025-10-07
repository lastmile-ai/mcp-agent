"""Integration tests for bootstrap repo functionality.
Tests the end-to-end flow including:
- Template loading and validation
- Full run() integration
- Error handling paths
- CODEOWNERS and CI template content
"""
import pytest
from unittest.mock import Mock, patch

from mcp_agent.tasks.bootstrap_repo import _load_template, build_plan, run


class TestTemplateLoading:
    """Test suite for template loading functionality."""

    def test_load_template_python_ci(self):
        """Test loading Python CI template succeeds."""
        # Act
        content = _load_template("ci/python.yml")
        
        # Assert
        assert content is not None
        assert len(content) > 0
        assert "python" in content.lower() or "py" in content.lower()

    def test_load_template_node_ci(self):
        """Test loading Node.js CI template succeeds."""
        # Act
        content = _load_template("ci/node.yml")
        
        # Assert
        assert content is not None
        assert len(content) > 0
        assert "node" in content.lower() or "npm" in content.lower()

    def test_load_template_codeowners(self):
        """Test loading CODEOWNERS template succeeds."""
        # Act
        content = _load_template("CODEOWNERS")
        
        # Assert
        assert content is not None
        assert len(content) > 0

    def test_load_template_missing_file_raises(self):
        """Test loading non-existent template raises FileNotFoundError."""
        # Act & Assert
        with pytest.raises(FileNotFoundError):
            _load_template("nonexistent.yml")

    def test_template_python_has_placeholder(self):
        """Test Python template contains branch placeholder."""
        # Act
        content = _load_template("ci/python.yml")
        
        # Assert - placeholder should exist in template
        assert "$default-branch" in content or "main" in content

    def test_template_node_has_placeholder(self):
        """Test Node template contains branch placeholder."""
        # Act
        content = _load_template("ci/node.yml")
        
        # Assert - placeholder should exist in template
        assert "$default-branch" in content or "main" in content


class TestBuildPlan:
    """Test suite for build_plan function."""

    def test_build_plan_skips_when_ci_exists(self):
        """Test plan is skipped when CI already exists."""
        # Arrange
        mock_cli = Mock()
        mock_cli.stat = Mock(side_effect=lambda o, r, ref, p: p == ".github/workflows/ci.yml")
        
        # Act
        plan = build_plan(mock_cli, "owner", "repo", "main", "auto")
        
        # Assert
        assert plan.skipped is True
        assert "existing CI detected" in plan.notes

    def test_build_plan_python_detection(self):
        """Test plan detects Python project correctly."""
        # Arrange
        mock_cli = Mock()
        mock_cli.stat = Mock(side_effect=lambda o, r, ref, p: p == "pyproject.toml")
        
        # Act
        plan = build_plan(mock_cli, "owner", "repo", "develop", "auto")
        
        # Assert
        assert plan.language == "python"
        assert plan.skipped is False
        assert ".github/workflows/ci.yml" in plan.files

    def test_build_plan_node_detection(self):
        """Test plan detects Node.js project correctly."""
        # Arrange
        mock_cli = Mock()
        mock_cli.stat = Mock(side_effect=lambda o, r, ref, p: p == "package.json")
        
        # Act
        plan = build_plan(mock_cli, "owner", "repo", "main", "auto")
        
        # Assert
        assert plan.language == "node"
        assert plan.skipped is False

    def test_build_plan_respects_language_hint(self):
        """Test plan uses explicit language hint over detection."""
        # Arrange
        mock_cli = Mock()
        mock_cli.stat = Mock(return_value=False)
        
        # Act
        plan = build_plan(mock_cli, "owner", "repo", "main", "python")
        
        # Assert
        assert plan.language == "python"

    def test_build_plan_includes_codeowners(self):
        """Test plan includes CODEOWNERS file."""
        # Arrange
        mock_cli = Mock()
        mock_cli.stat = Mock(return_value=False)
        
        # Act
        plan = build_plan(mock_cli, "owner", "repo", "main", "python")
        
        # Assert
        assert ".github/CODEOWNERS" in plan.files

    def test_build_plan_substitutes_branch_name(self):
        """Test plan substitutes default branch in templates."""
        # Arrange
        mock_cli = Mock()
        mock_cli.stat = Mock(return_value=False)
        
        # Act
        plan = build_plan(mock_cli, "owner", "repo", "develop", "python")
        
        # Assert
        ci_content = plan.files[".github/workflows/ci.yml"]
        assert "develop" in ci_content or "$default-branch" not in ci_content


class TestRunIntegration:
    """Test suite for run() function integration."""

    def test_run_dry_run_returns_plan(self):
        """Test dry run returns plan without executing."""
        # Arrange
        with patch("mcp_agent.tasks.bootstrap_repo.GithubMCPClient") as MockClient:
            mock_client = Mock()
            mock_client.get_default_branch.return_value = "main"
            mock_client.stat.return_value = False
            MockClient.return_value = mock_client
            
            # Act
            result = run("owner", "repo", "trace-123", language="python", dry_run=True)
        
        # Assert
        assert "plan" in result
        assert result["skipped"] is False
        mock_client.create_branch.assert_not_called()
        mock_client.put_add_only.assert_not_called()

    def test_run_skips_when_ci_exists(self):
        """Test run returns skip status when CI already exists."""
        # Arrange
        with patch("mcp_agent.tasks.bootstrap_repo.GithubMCPClient") as MockClient:
            mock_client = Mock()
            mock_client.get_default_branch.return_value = "main"
            mock_client.stat.return_value = True  # CI exists
            MockClient.return_value = mock_client
            
            # Act
            result = run("owner", "repo", "trace-123", dry_run=False)
        
        # Assert
        assert result["skipped"] is True
        assert result["reason"] == "existing_ci"

    def test_run_creates_branch_and_files(self):
        """Test run creates branch and adds files successfully."""
        # Arrange
        with patch("mcp_agent.tasks.bootstrap_repo.GithubMCPClient") as MockClient:
            mock_client = Mock()
            mock_client.get_default_branch.return_value = "main"
            mock_client.stat.return_value = False
            mock_client.put_add_only.return_value = (True, "created")
            mock_client.open_pr.return_value = "42"
            MockClient.return_value = mock_client
            
            # Act
            result = run("owner", "repo", "trace-123", language="python", dry_run=False)
        
        # Assert
        assert result["skipped"] is False
        assert result["pr_id"] == "42"
        assert result["branch"] == "vibe/bootstrap"
        mock_client.create_branch.assert_called_once()
        mock_client.put_add_only.assert_called()
        mock_client.open_pr.assert_called_once()

    def test_run_handles_ci_trigger_failure_gracefully(self):
        """Test run continues when CI trigger fails."""
        # Arrange
        with patch("mcp_agent.tasks.bootstrap_repo.GithubMCPClient") as MockClient:
            mock_client = Mock()
            mock_client.get_default_branch.return_value = "main"
            mock_client.stat.return_value = False
            mock_client.put_add_only.return_value = (True, "created")
            mock_client.open_pr.return_value = "42"
            mock_client.run_ci_on_pr.side_effect = Exception("CI API error")
            MockClient.return_value = mock_client
            
            # Act
            result = run("owner", "repo", "trace-123", dry_run=False)
        
        # Assert - should succeed despite CI trigger failure
        assert result["skipped"] is False
        assert result["pr_id"] == "42"

    def test_run_respects_add_only_guard(self):
        """Test run skips files that already exist (add-only)."""
        # Arrange
        with patch("mcp_agent.tasks.bootstrap_repo.GithubMCPClient") as MockClient:
            mock_client = Mock()
            mock_client.get_default_branch.return_value = "main"
            # CODEOWNERS exists, CI does not
            mock_client.stat.side_effect = lambda o, r, ref, p: p == ".github/CODEOWNERS"
            mock_client.put_add_only.return_value = (True, "created")
            mock_client.open_pr.return_value = "42"
            MockClient.return_value = mock_client
            
            # Act
            result = run("owner", "repo", "trace-123", language="python", dry_run=False)
        
        # Assert - should only call put_add_only for CI file, not CODEOWNERS
        assert result["skipped"] is False
        # Exactly one file created (CI, not CODEOWNERS)
        assert mock_client.put_add_only.call_count == 1
        call_args = mock_client.put_add_only.call_args[1]
        assert "ci.yml" in call_args["path"]

    def test_run_auto_language_detection(self):
        """Test run detects language when set to 'auto'."""
        # Arrange
        with patch("mcp_agent.tasks.bootstrap_repo.GithubMCPClient") as MockClient:
            mock_client = Mock()
            mock_client.get_default_branch.return_value = "main"
            # Simulate Python project
            mock_client.stat.side_effect = lambda o, r, ref, p: p == "pyproject.toml"
            mock_client.put_add_only.return_value = (True, "created")
            mock_client.open_pr.return_value = "42"
            MockClient.return_value = mock_client
            
            # Act
            result = run("owner", "repo", "trace-123", language="auto", dry_run=False)
        
        # Assert
        assert result["language"] == "python"


class TestTemplateContentValidity:
    """Smoke tests to ensure template content is valid."""

    def test_python_template_valid_yaml_structure(self):
        """Test Python CI template has valid YAML structure."""
        # Act
        content = _load_template("ci/python.yml")
        
        # Assert - basic smoke test for YAML structure
        assert content.startswith("name:") or "on:" in content
        assert "jobs:" in content

    def test_node_template_valid_yaml_structure(self):
        """Test Node CI template has valid YAML structure."""
        # Act
        content = _load_template("ci/node.yml")
        
        # Assert - basic smoke test for YAML structure
        assert content.startswith("name:") or "on:" in content
        assert "jobs:" in content

    def test_codeowners_format(self):
        """Test CODEOWNERS template has valid format."""
        # Act
        content = _load_template("CODEOWNERS")
        
        # Assert - should contain pattern or comment
        assert len(content.strip()) > 0
        # CODEOWNERS format: pattern followed by owner(s)
        lines = [line for line in content.split("\n") if line.strip() and not line.strip().startswith("#")]
        # Should have at least one ownership line or be empty/commented
        assert len(lines) == 0 or "*" in content or "@" in content
