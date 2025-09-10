"""Tests for the wrangler wrapper functionality."""

import os
import subprocess
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from mcp_agent.cli.cloud.commands.deploy.validation import (
    validate_entrypoint,
    validate_project,
)
from mcp_agent.cli.cloud.commands.deploy.wrangler_wrapper import (
    _modify_requirements_txt,
    _needs_requirements_modification,
    wrangler_deploy,
)


@pytest.fixture
def valid_project_dir():
    """Create a temporary directory with valid project structure."""
    with tempfile.TemporaryDirectory() as temp_dir:
        project_path = Path(temp_dir)

        # Create a valid main.py with MCPApp definition
        main_py_content = """from mcp_agent_cloud import MCPApp

app = MCPApp(
    name="test-app",
    description="A test MCP Agent"
)
"""
        main_py_path = project_path / "main.py"
        main_py_path.write_text(main_py_content)

        yield project_path


@pytest.fixture
def project_with_requirements():
    """Create a temporary directory with requirements.txt."""
    with tempfile.TemporaryDirectory() as temp_dir:
        project_path = Path(temp_dir)

        # Create main.py
        main_py_content = """from mcp_agent_cloud import MCPApp

app = MCPApp(name="test-app")
"""
        (project_path / "main.py").write_text(main_py_content)

        # Create requirements.txt
        (project_path / "requirements.txt").write_text(
            "requests==2.31.0\nnumpy==1.24.0"
        )

        yield project_path


@pytest.fixture
def project_with_poetry():
    """Create a temporary directory with poetry configuration."""
    with tempfile.TemporaryDirectory() as temp_dir:
        project_path = Path(temp_dir)

        # Create main.py
        main_py_content = """from mcp_agent_cloud import MCPApp

app = MCPApp(name="test-app")
"""
        (project_path / "main.py").write_text(main_py_content)

        # Create pyproject.toml
        pyproject_content = """[tool.poetry]
name = "test-app"
version = "0.1.0"

[tool.poetry.dependencies]
python = "^3.8"
"""
        (project_path / "pyproject.toml").write_text(pyproject_content)

        # Create poetry.lock
        (project_path / "poetry.lock").write_text("# Poetry lock file content")

        yield project_path


@pytest.fixture
def project_with_uv():
    """Create a temporary directory with uv configuration."""
    with tempfile.TemporaryDirectory() as temp_dir:
        project_path = Path(temp_dir)

        # Create main.py
        main_py_content = """from mcp_agent_cloud import MCPApp

app = MCPApp(name="test-app")
"""
        (project_path / "main.py").write_text(main_py_content)

        # Create pyproject.toml
        pyproject_content = """[project]
name = "test-app"
version = "0.1.0"
"""
        (project_path / "pyproject.toml").write_text(pyproject_content)

        # Create uv.lock
        (project_path / "uv.lock").write_text("# UV lock file content")

        yield project_path


@pytest.fixture
def complex_project_structure():
    """Create a complex project structure with nested files and various file types."""
    with tempfile.TemporaryDirectory() as temp_dir:
        project_path = Path(temp_dir)

        # Create main.py
        main_py_content = """from mcp_agent_cloud import MCPApp

app = MCPApp(name="complex-test-app")
"""
        (project_path / "main.py").write_text(main_py_content)

        # Create various config files in root
        (project_path / "README.md").write_text("# Test Project")
        (project_path / "config.json").write_text('{"test": true}')
        (project_path / "data.txt").write_text("test data")
        (project_path / "requirements.txt").write_text("requests==2.31.0")

        # Create nested directory structure
        nested_dir = project_path / "nested"
        nested_dir.mkdir()
        (nested_dir / "nested_config.yaml").write_text("key: value")
        (nested_dir / "nested_script.py").write_text("print('nested')")
        (nested_dir / "nested_data.csv").write_text("col1,col2\n1,2")

        # Create deeply nested structure
        deep_nested = nested_dir / "deep"
        deep_nested.mkdir()
        (deep_nested / "deep_file.txt").write_text("deep content")

        # Create directories that should be excluded
        logs_dir = project_path / "logs"
        logs_dir.mkdir()
        (logs_dir / "app.log").write_text("log content")

        dot_dir = project_path / ".git"
        dot_dir.mkdir()
        (dot_dir / "config").write_text("git config")

        venv_dir = project_path / ".venv"
        venv_dir.mkdir()
        (venv_dir / "lib").mkdir()

        # Create hidden files (should be skipped)
        (project_path / ".hidden").write_text("hidden content")

        yield project_path


# Validation Tests (moved from test_deploy_command.py)


def test_validate_project_success(valid_project_dir):
    """Test validate_project with a valid project structure."""
    # Should not raise any exceptions
    validate_project(valid_project_dir)


def test_validate_project_missing_directory():
    """Test validate_project with non-existent directory."""
    with pytest.raises(FileNotFoundError, match="Project directory .* does not exist"):
        validate_project(Path("/non/existent/path"))


def test_validate_project_missing_main_py():
    """Test validate_project with missing main.py."""
    with tempfile.TemporaryDirectory() as temp_dir:
        project_path = Path(temp_dir)

        with pytest.raises(FileNotFoundError, match="Required file main.py is missing"):
            validate_project(project_path)


def test_validate_project_with_requirements_txt(project_with_requirements):
    """Test validate_project with requirements.txt dependency management."""
    # Should not raise any exceptions
    validate_project(project_with_requirements)


def test_validate_project_with_poetry(project_with_poetry):
    """Test validate_project with poetry dependency management."""
    # Should not raise any exceptions
    validate_project(project_with_poetry)


def test_validate_project_with_uv(project_with_uv):
    """Test validate_project with uv dependency management."""
    # Should not raise any exceptions
    validate_project(project_with_uv)


def test_validate_project_multiple_dependency_managers():
    """Test validate_project with multiple dependency management files."""
    with tempfile.TemporaryDirectory() as temp_dir:
        project_path = Path(temp_dir)

        # Create main.py
        main_py_content = """from mcp_agent_cloud import MCPApp

app = MCPApp(name="test-app")
"""
        (project_path / "main.py").write_text(main_py_content)

        # Create multiple dependency files
        (project_path / "requirements.txt").write_text("requests==2.31.0")
        (project_path / "poetry.lock").write_text("# Poetry lock")

        with pytest.raises(
            ValueError,
            match="Multiple Python project dependency management files found",
        ):
            validate_project(project_path)


def test_validate_project_uv_without_pyproject():
    """Test validate_project with uv.lock but no pyproject.toml."""
    with tempfile.TemporaryDirectory() as temp_dir:
        project_path = Path(temp_dir)

        # Create main.py
        main_py_content = """from mcp_agent_cloud import MCPApp

app = MCPApp(name="test-app")
"""
        (project_path / "main.py").write_text(main_py_content)

        # Create uv.lock without pyproject.toml
        (project_path / "uv.lock").write_text("# UV lock file")

        with pytest.raises(
            ValueError,
            match="Invalid uv project: uv.lock found without corresponding pyproject.toml",
        ):
            validate_project(project_path)


def test_validate_project_poetry_without_pyproject():
    """Test validate_project with poetry.lock but no pyproject.toml."""
    with tempfile.TemporaryDirectory() as temp_dir:
        project_path = Path(temp_dir)

        # Create main.py
        main_py_content = """from mcp_agent_cloud import MCPApp

app = MCPApp(name="test-app")
"""
        (project_path / "main.py").write_text(main_py_content)

        # Create poetry.lock without pyproject.toml
        (project_path / "poetry.lock").write_text("# Poetry lock file")

        with pytest.raises(
            ValueError,
            match="Invalid poetry project: poetry.lock found without corresponding pyproject.toml",
        ):
            validate_project(project_path)


def test_validate_entrypoint_success(valid_project_dir):
    """Test validate_entrypoint with valid MCPApp definition."""
    entrypoint_path = valid_project_dir / "main.py"
    # Should not raise any exceptions
    validate_entrypoint(entrypoint_path)


def test_validate_entrypoint_missing_file():
    """Test validate_entrypoint with non-existent file."""
    with pytest.raises(FileNotFoundError, match="Entrypoint file .* does not exist"):
        validate_entrypoint(Path("/non/existent/main.py"))


def test_validate_entrypoint_no_mcp_app():
    """Test validate_entrypoint without MCPApp definition."""
    with tempfile.TemporaryDirectory() as temp_dir:
        main_py_path = Path(temp_dir) / "main.py"

        # Create main.py without MCPApp
        main_py_content = """
def main():
    print("Hello, world!")

if __name__ == "__main__":
    main()
"""
        main_py_path.write_text(main_py_content)

        with pytest.raises(ValueError, match="No MCPApp definition found in main.py"):
            validate_entrypoint(main_py_path)


def test_validate_entrypoint_with_main_block_warning(capsys):
    """Test validate_entrypoint with __main__ block shows warning."""
    with tempfile.TemporaryDirectory() as temp_dir:
        main_py_path = Path(temp_dir) / "main.py"

        # Create main.py with MCPApp and __main__ block
        main_py_content = """from mcp_agent_cloud import MCPApp

app = MCPApp(name="test-app")

if __name__ == "__main__":
    print("This will be ignored")
"""
        main_py_path.write_text(main_py_content)

        # Should not raise exception but should print warning
        validate_entrypoint(main_py_path)

        # Check if warning was printed to stderr
        captured = capsys.readouterr()
        assert (
            "Found a __main__ entrypoint in main.py. This will be ignored"
            in captured.err
            or "Found a __main__ entrypoint in main.py. This will be ignored"
            in captured.out
        )


def test_validate_entrypoint_multiline_mcp_app():
    """Test validate_entrypoint with multiline MCPApp definition."""
    with tempfile.TemporaryDirectory() as temp_dir:
        main_py_path = Path(temp_dir) / "main.py"

        # Create main.py with multiline MCPApp
        main_py_content = """from mcp_agent_cloud import MCPApp

my_app = MCPApp(
    name="test-app",
    description="A test application",
    version="1.0.0"
)
"""
        main_py_path.write_text(main_py_content)

        # Should not raise any exceptions
        validate_entrypoint(main_py_path)


def test_validate_entrypoint_different_variable_names():
    """Test validate_entrypoint with different variable names for MCPApp."""
    with tempfile.TemporaryDirectory() as temp_dir:
        main_py_path = Path(temp_dir) / "main.py"

        # Test various variable names
        for var_name in ["app", "my_app", "application", "mcp_app"]:
            main_py_content = f"""from mcp_agent_cloud import MCPApp

{var_name} = MCPApp(name="test-app")
"""
            main_py_path.write_text(main_py_content)

            # Should not raise any exceptions
            validate_entrypoint(main_py_path)


def test_wrangler_deploy_file_copying(complex_project_structure):
    """Test that wrangler_deploy correctly copies non-Python files with .mcpac.py extension."""

    def check_files_during_subprocess(*args, **kwargs):
        # During subprocess execution, .mcpac.py files should exist
        assert (complex_project_structure / "README.md.mcpac.py").exists()
        assert (complex_project_structure / "config.json.mcpac.py").exists()
        assert (complex_project_structure / "data.txt.mcpac.py").exists()
        assert (complex_project_structure / "requirements.txt.mcpac.py").exists()
        assert (
            complex_project_structure / "nested/nested_config.yaml.mcpac.py"
        ).exists()
        assert (complex_project_structure / "nested/nested_data.csv.mcpac.py").exists()
        assert (
            complex_project_structure / "nested/deep/deep_file.txt.mcpac.py"
        ).exists()

        # Check that Python files were NOT copied
        assert not (
            complex_project_structure / "nested/nested_script.py.mcpac.py"
        ).exists()

        # Check that excluded directories' files were NOT copied
        assert not (complex_project_structure / "logs/app.log.mcpac.py").exists()
        assert not (complex_project_structure / ".git/config.mcpac.py").exists()
        assert not (
            complex_project_structure / ".venv"
        ).exists()  # .venv should be moved

        # Check that hidden files were NOT copied
        assert not (complex_project_structure / ".hidden.mcpac.py").exists()

        return MagicMock(returncode=0)

    with patch("subprocess.run", side_effect=check_files_during_subprocess):
        # Run wrangler_deploy
        wrangler_deploy("test-app", "test-api-key", complex_project_structure)

        # After deployment, .mcpac.py files should be cleaned up
        assert not (complex_project_structure / "README.md.mcpac.py").exists()
        assert not (complex_project_structure / "config.json.mcpac.py").exists()


def test_wrangler_deploy_file_content_preservation(complex_project_structure):
    """Test that file content is preserved when copying with .mcpac.py extension."""
    original_content = "# Test Project Content"
    (complex_project_structure / "README.md").write_text(original_content)

    def check_content_during_subprocess(*args, **kwargs):
        # Check that content is preserved in the .mcpac.py copy during subprocess
        mcpac_file = complex_project_structure / "README.md.mcpac.py"
        assert mcpac_file.exists()
        assert mcpac_file.read_text() == original_content
        return MagicMock(returncode=0)

    with patch("subprocess.run", side_effect=check_content_during_subprocess):
        wrangler_deploy("test-app", "test-api-key", complex_project_structure)

        # After deployment, .mcpac.py file should be cleaned up but original should exist
        assert not (complex_project_structure / "README.md.mcpac.py").exists()
        assert (complex_project_structure / "README.md").exists()
        assert (complex_project_structure / "README.md").read_text() == original_content


def test_wrangler_deploy_original_file_hiding(complex_project_structure):
    """Test that original non-Python files are temporarily hidden during deployment."""
    original_files = [
        "README.md",
        "config.json",
        "data.txt",
        "requirements.txt",
        "nested/nested_config.yaml",
        "nested/nested_data.csv",
    ]

    def check_files_during_subprocess(*args, **kwargs):
        # During subprocess execution, original files should be hidden (.bak)
        for file_path in original_files:
            original_file = complex_project_structure / file_path
            bak_file = complex_project_structure / f"{file_path}.bak"

            # Original should not exist, .bak should exist
            assert not original_file.exists(), f"{file_path} should be hidden"
            assert bak_file.exists(), f"{file_path}.bak should exist"

        return MagicMock(returncode=0)

    with patch("subprocess.run", side_effect=check_files_during_subprocess):
        wrangler_deploy("test-app", "test-api-key", complex_project_structure)

    # After deployment, original files should be restored
    for file_path in original_files:
        original_file = complex_project_structure / file_path
        bak_file = complex_project_structure / f"{file_path}.bak"

        assert original_file.exists(), f"{file_path} should be restored"
        assert not bak_file.exists(), f"{file_path}.bak should be cleaned up"


def test_wrangler_deploy_cleanup_on_success(complex_project_structure):
    """Test that temporary files are cleaned up after successful deployment."""
    with patch("subprocess.run") as mock_subprocess:
        mock_subprocess.return_value = MagicMock(returncode=0)

        wrangler_deploy("test-app", "test-api-key", complex_project_structure)

        # Check that .mcpac.py files are cleaned up
        assert not (complex_project_structure / "README.md.mcpac.py").exists()
        assert not (complex_project_structure / "config.json.mcpac.py").exists()
        assert not (
            complex_project_structure / "nested/nested_config.yaml.mcpac.py"
        ).exists()

        # Check that original files are restored
        assert (complex_project_structure / "README.md").exists()
        assert (complex_project_structure / "config.json").exists()
        assert (complex_project_structure / "nested/nested_config.yaml").exists()

        # Check that wrangler.toml is cleaned up
        assert not (complex_project_structure / "wrangler.toml").exists()


def test_wrangler_deploy_cleanup_on_failure(complex_project_structure):
    """Test that temporary files are cleaned up even when deployment fails."""
    with patch("subprocess.run") as mock_subprocess:
        # Mock failed subprocess call
        mock_subprocess.side_effect = subprocess.CalledProcessError(
            returncode=1, cmd=["wrangler"], stderr="Deployment failed"
        )

        # Should raise exception but still clean up
        with pytest.raises(subprocess.CalledProcessError):
            wrangler_deploy("test-app", "test-api-key", complex_project_structure)

        # Check that .mcpac.py files are cleaned up even on failure
        assert not (complex_project_structure / "README.md.mcpac.py").exists()
        assert not (complex_project_structure / "config.json.mcpac.py").exists()

        # Check that original files are restored even on failure
        assert (complex_project_structure / "README.md").exists()
        assert (complex_project_structure / "config.json").exists()

        # Check that wrangler.toml is cleaned up even on failure
        assert not (complex_project_structure / "wrangler.toml").exists()


def test_wrangler_deploy_venv_handling(complex_project_structure):
    """Test that .venv directory is properly moved and restored."""
    # Ensure .venv exists
    venv_dir = complex_project_structure / ".venv"
    assert venv_dir.exists()

    # Add some content to .venv
    (venv_dir / "test_file").write_text("venv content")

    def check_venv_during_subprocess(*args, **kwargs):
        # During subprocess execution, .venv should not exist in project dir
        assert not venv_dir.exists(), ".venv should be moved out of project dir"
        return MagicMock(returncode=0)

    with patch("subprocess.run", side_effect=check_venv_during_subprocess):
        wrangler_deploy("test-app", "test-api-key", complex_project_structure)

    # After deployment, .venv should be restored
    assert venv_dir.exists(), ".venv should be restored"
    assert (venv_dir / "test_file").exists(), ".venv content should be preserved"
    assert (venv_dir / "test_file").read_text() == "venv content"


def test_wrangler_deploy_directory_exclusion(complex_project_structure):
    """Test that specific directories are properly excluded from file processing."""
    # Add more files to excluded directories
    cache_dir = complex_project_structure / "__pycache__"
    cache_dir.mkdir()
    (cache_dir / "test.pyc").write_text("compiled python")

    node_modules = complex_project_structure / "node_modules"
    node_modules.mkdir()
    (node_modules / "package.json").write_text("{}")

    with patch("subprocess.run") as mock_subprocess:
        mock_subprocess.return_value = MagicMock(returncode=0)

        wrangler_deploy("test-app", "test-api-key", complex_project_structure)

        # Check that files in excluded directories were not processed
        assert not (complex_project_structure / "logs/app.log.mcpac.py").exists()
        assert not (
            complex_project_structure / "__pycache__/test.pyc.mcpac.py"
        ).exists()
        assert not (
            complex_project_structure / "node_modules/package.json.mcpac.py"
        ).exists()


def test_wrangler_deploy_nested_directory_creation(complex_project_structure):
    """Test that nested directory structure is preserved when creating .mcpac.py files."""
    nested_mcpac = complex_project_structure / "nested/nested_config.yaml.mcpac.py"
    deep_mcpac = complex_project_structure / "nested/deep/deep_file.txt.mcpac.py"

    def check_nested_files_during_subprocess(*args, **kwargs):
        # During subprocess execution, .mcpac.py files should exist in nested directories
        assert nested_mcpac.exists(), (
            "Nested .mcpac.py file should exist during subprocess"
        )
        assert deep_mcpac.exists(), (
            "Deep nested .mcpac.py file should exist during subprocess"
        )

        # Check that the nested directory structure is preserved
        assert nested_mcpac.parent == complex_project_structure / "nested"
        assert deep_mcpac.parent == complex_project_structure / "nested/deep"

        return MagicMock(returncode=0)

    with patch("subprocess.run", side_effect=check_nested_files_during_subprocess):
        wrangler_deploy("test-app", "test-api-key", complex_project_structure)

        # After cleanup, originals should exist and .mcpac.py should not
        assert (complex_project_structure / "nested/nested_config.yaml").exists()
        assert (complex_project_structure / "nested/deep/deep_file.txt").exists()
        assert not nested_mcpac.exists()
        assert not deep_mcpac.exists()


def test_wrangler_deploy_empty_files(complex_project_structure):
    """Test handling of empty files."""
    # Create an empty file
    empty_file = complex_project_structure / "empty.txt"
    empty_file.write_text("")

    with patch("subprocess.run") as mock_subprocess:
        mock_subprocess.return_value = MagicMock(returncode=0)

        wrangler_deploy("test-app", "test-api-key", complex_project_structure)

        # After deployment, empty file should still exist and be empty
        assert empty_file.exists()
        assert empty_file.read_text() == ""


def test_wrangler_deploy_file_permissions_preserved(complex_project_structure):
    """Test that file permissions are preserved when copying files."""
    test_file = complex_project_structure / "executable.sh"
    test_file.write_text("#!/bin/bash\necho 'test'")

    # Make file executable (if on Unix-like system)
    if hasattr(os, "chmod"):
        os.chmod(test_file, 0o755)

    with patch("subprocess.run") as mock_subprocess:
        mock_subprocess.return_value = MagicMock(returncode=0)

        wrangler_deploy("test-app", "test-api-key", complex_project_structure)

        # File should still exist and have original content
        assert test_file.exists()
        assert "#!/bin/bash" in test_file.read_text()


def test_wrangler_deploy_special_filenames():
    """Test handling of files with special characters in names."""
    with tempfile.TemporaryDirectory() as temp_dir:
        project_path = Path(temp_dir)

        # Create main.py
        (project_path / "main.py").write_text("""
from mcp_agent_cloud import MCPApp
app = MCPApp(name="test-app")
""")

        # Create files with special characters
        special_files = [
            "file with spaces.txt",
            "file-with-dashes.json",
            "file_with_underscores.yaml",
            "file.with.dots.config",
        ]

        for filename in special_files:
            (project_path / filename).write_text(f"Content of {filename}")

        with patch("subprocess.run") as mock_subprocess:
            mock_subprocess.return_value = MagicMock(returncode=0)

            # Should not raise exceptions
            wrangler_deploy("test-app", "test-api-key", project_path)

            # All special files should still exist after cleanup
            for filename in special_files:
                assert (project_path / filename).exists()


def test_wrangler_deploy_complex_file_extensions():
    """Test handling of files with complex extensions (e.g., .tar.gz, .config.json)."""
    with tempfile.TemporaryDirectory() as temp_dir:
        project_path = Path(temp_dir)

        # Create main.py
        (project_path / "main.py").write_text("""
from mcp_agent_cloud import MCPApp
app = MCPApp(name="test-app")
""")

        # Create files with complex extensions that would break with .with_suffix()
        complex_files = {
            "archive.tar.gz": "archive content",
            "config.json.template": "template content",
            "data.csv.backup": "backup data",
            "script.sh.orig": "original script",
            "file.name.with.multiple.dots.txt": "multi-dot content",
        }

        for filename, content in complex_files.items():
            (project_path / filename).write_text(content)

        def check_complex_extensions_during_subprocess(*args, **kwargs):
            # During subprocess, .bak files should exist and .mcpac.py files should exist
            for filename in complex_files.keys():
                bak_file = project_path / f"{filename}.bak"
                mcpac_file = project_path / f"{filename}.mcpac.py"

                assert bak_file.exists(), (
                    f"{filename}.bak should exist during subprocess"
                )
                assert mcpac_file.exists(), (
                    f"{filename}.mcpac.py should exist during subprocess"
                )

                # Original should not exist during subprocess
                original_file = project_path / filename
                assert not original_file.exists(), (
                    f"{filename} should be hidden during subprocess"
                )

            return MagicMock(returncode=0)

        with patch(
            "subprocess.run", side_effect=check_complex_extensions_during_subprocess
        ):
            wrangler_deploy("test-app", "test-api-key", project_path)

            # After cleanup, original files should exist with correct content
            for filename, expected_content in complex_files.items():
                original_file = project_path / filename
                bak_file = project_path / f"{filename}.bak"
                mcpac_file = project_path / f"{filename}.mcpac.py"

                assert original_file.exists(), f"{filename} should be restored"
                assert original_file.read_text() == expected_content, (
                    f"{filename} content should be preserved"
                )
                assert not bak_file.exists(), f"{filename}.bak should be cleaned up"
                assert not mcpac_file.exists(), (
                    f"{filename}.mcpac.py should be cleaned up"
                )


# Requirements.txt processing tests


def test_needs_requirements_modification_no_file():
    """Test _needs_requirements_modification when requirements.txt doesn't exist."""
    with tempfile.TemporaryDirectory() as temp_dir:
        requirements_path = Path(temp_dir) / "requirements.txt"
        assert not _needs_requirements_modification(requirements_path)


def test_needs_requirements_modification_no_relative_imports():
    """Test _needs_requirements_modification with no relative mcp-agent imports."""
    with tempfile.TemporaryDirectory() as temp_dir:
        requirements_path = Path(temp_dir) / "requirements.txt"
        requirements_path.write_text("""requests==2.31.0
numpy==1.24.0
mcp-agent==1.0.0
pandas>=1.0.0""")

        assert not _needs_requirements_modification(requirements_path)


def test_needs_requirements_modification_with_relative_imports():
    """Test _needs_requirements_modification with relative mcp-agent imports."""
    with tempfile.TemporaryDirectory() as temp_dir:
        requirements_path = Path(temp_dir) / "requirements.txt"

        # Test various relative import formats
        test_cases = [
            "mcp-agent @ file://../../",
            "mcp-agent@file://../../",
            "mcp-agent  @  file://../../some/path",
            "mcp-agent @ file:///absolute/path",
        ]

        for relative_import in test_cases:
            requirements_content = f"""requests==2.31.0
{relative_import}
numpy==1.24.0"""
            requirements_path.write_text(requirements_content)
            assert _needs_requirements_modification(requirements_path), (
                f"Should detect relative import: {relative_import}"
            )


def test_needs_requirements_modification_mixed_content():
    """Test _needs_requirements_modification with mixed content."""
    with tempfile.TemporaryDirectory() as temp_dir:
        requirements_path = Path(temp_dir) / "requirements.txt"
        requirements_content = """# This is a requirements file
requests==2.31.0
numpy==1.24.0
mcp-agent @ file://../../
pandas>=1.0.0
# Comment line
fastapi==0.68.0"""
        requirements_path.write_text(requirements_content)

        assert _needs_requirements_modification(requirements_path)


def test_modify_requirements_txt_relative_import():
    """Test _modify_requirements_txt with relative import."""
    with tempfile.TemporaryDirectory() as temp_dir:
        requirements_path = Path(temp_dir) / "requirements.txt"
        original_content = """requests==2.31.0
mcp-agent @ file://../../
numpy==1.24.0"""
        requirements_path.write_text(original_content)

        _modify_requirements_txt(requirements_path)

        modified_content = requirements_path.read_text()
        expected_content = """requests==2.31.0
mcp-agent
numpy==1.24.0"""

        assert modified_content == expected_content


def test_modify_requirements_txt_preserves_formatting():
    """Test _modify_requirements_txt preserves comments and formatting."""
    with tempfile.TemporaryDirectory() as temp_dir:
        requirements_path = Path(temp_dir) / "requirements.txt"
        original_content = """# Project dependencies
requests==2.31.0
# Development version of mcp-agent
mcp-agent @ file://../../

# Data processing
numpy==1.24.0
pandas>=1.0.0
"""
        requirements_path.write_text(original_content)

        _modify_requirements_txt(requirements_path)

        modified_content = requirements_path.read_text()
        expected_content = """# Project dependencies
requests==2.31.0
# Development version of mcp-agent
mcp-agent

# Data processing
numpy==1.24.0
pandas>=1.0.0
"""

        assert modified_content == expected_content


@pytest.fixture
def project_with_relative_mcp_agent():
    """Create a project with requirements.txt containing relative mcp-agent import."""
    with tempfile.TemporaryDirectory() as temp_dir:
        project_path = Path(temp_dir)

        # Create main.py
        main_py_content = """from mcp_agent_cloud import MCPApp

app = MCPApp(name="test-app")
"""
        (project_path / "main.py").write_text(main_py_content)

        # Create requirements.txt with relative mcp-agent import
        requirements_content = """requests==2.31.0
mcp-agent @ file://../../
numpy==1.24.0"""
        (project_path / "requirements.txt").write_text(requirements_content)

        yield project_path


def test_wrangler_deploy_requirements_txt_backup_and_restore(
    project_with_relative_mcp_agent,
):
    """Test that requirements.txt is backed up, modified, and restored during deployment."""
    requirements_path = project_with_relative_mcp_agent / "requirements.txt"
    original_content = requirements_path.read_text()

    def check_requirements_during_subprocess(*args, **kwargs):
        # During subprocess execution, requirements.txt should be modified
        current_content = requirements_path.read_text()
        assert "mcp-agent @ file://" not in current_content
        assert "mcp-agent\n" in current_content

        return MagicMock(returncode=0)

    with patch("subprocess.run", side_effect=check_requirements_during_subprocess):
        wrangler_deploy("test-app", "test-api-key", project_with_relative_mcp_agent)

    # After deployment, requirements.txt should be restored to original content
    restored_content = requirements_path.read_text()
    assert restored_content == original_content
    assert "mcp-agent @ file://../../" in restored_content


def test_wrangler_deploy_requirements_txt_no_modification_needed(
    project_with_requirements,
):
    """Test that requirements.txt without relative imports follows normal file processing."""
    requirements_path = project_with_requirements / "requirements.txt"
    original_content = requirements_path.read_text()

    def check_requirements_during_subprocess(*args, **kwargs):
        # During subprocess, requirements.txt should be hidden (.bak) and .mcpac.py should exist
        # since it doesn't need special modification
        bak_path = project_with_requirements / "requirements.txt.bak"
        mcpac_path = project_with_requirements / "requirements.txt.mcpac.py"

        assert not requirements_path.exists(), (
            "Original requirements.txt should be hidden"
        )
        assert bak_path.exists(), "requirements.txt.bak should exist"
        assert mcpac_path.exists(), "requirements.txt.mcpac.py should exist"

        # Content should be preserved in both .bak and .mcpac.py
        assert bak_path.read_text() == original_content
        assert mcpac_path.read_text() == original_content

        return MagicMock(returncode=0)

    with patch("subprocess.run", side_effect=check_requirements_during_subprocess):
        wrangler_deploy("test-app", "test-api-key", project_with_requirements)

    # After deployment, requirements.txt should be restored unchanged
    final_content = requirements_path.read_text()
    assert final_content == original_content


def test_wrangler_deploy_requirements_txt_restore_on_failure(
    project_with_relative_mcp_agent,
):
    """Test that requirements.txt is restored even when deployment fails."""
    requirements_path = project_with_relative_mcp_agent / "requirements.txt"
    original_content = requirements_path.read_text()

    with patch("subprocess.run") as mock_subprocess:
        # Mock failed subprocess call
        mock_subprocess.side_effect = subprocess.CalledProcessError(
            returncode=1, cmd=["wrangler"], stderr="Deployment failed"
        )

        # Should raise exception but still restore requirements.txt
        with pytest.raises(subprocess.CalledProcessError):
            wrangler_deploy("test-app", "test-api-key", project_with_relative_mcp_agent)

    # After failed deployment, requirements.txt should be restored
    restored_content = requirements_path.read_text()
    assert restored_content == original_content
    assert "mcp-agent @ file://../../" in restored_content


def test_wrangler_deploy_no_requirements_txt():
    """Test that deployment works normally when no requirements.txt exists."""
    with tempfile.TemporaryDirectory() as temp_dir:
        project_path = Path(temp_dir)

        # Create main.py only
        (project_path / "main.py").write_text("""
from mcp_agent_cloud import MCPApp
app = MCPApp(name="test-app")
""")

        with patch("subprocess.run") as mock_subprocess:
            mock_subprocess.return_value = MagicMock(returncode=0)

            # Should not raise any exceptions
            wrangler_deploy("test-app", "test-api-key", project_path)

        # No requirements.txt should exist after deployment
        assert not (project_path / "requirements.txt").exists()
