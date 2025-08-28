"""Tests for deploy validation functionality."""

import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest
from mcp_agent.cli.cloud.commands.deploy.validation import (
    validate_entrypoint,
    validate_project,
)


class TestValidateProject:
    """Tests for validate_project function."""

    def test_validate_project_success(self):
        """Test validation of a valid project directory."""
        with tempfile.TemporaryDirectory() as temp_dir:
            project_dir = Path(temp_dir)
            main_py = project_dir / "main.py"
            main_py.write_text("""
from mcp_agent.cloud import MCPApp

app = MCPApp(name="test-app")
""")

            # Should not raise any exception
            validate_project(project_dir)

    def test_validate_project_directory_not_exists(self):
        """Test validation fails when project directory doesn't exist."""
        non_existent_dir = Path("/non/existent/directory")

        with pytest.raises(
            FileNotFoundError, match="Project directory .* does not exist"
        ):
            validate_project(non_existent_dir)

    def test_validate_project_missing_main_py(self):
        """Test validation fails when main.py is missing."""
        with tempfile.TemporaryDirectory() as temp_dir:
            project_dir = Path(temp_dir)

            with pytest.raises(
                FileNotFoundError, match="Required file main.py is missing"
            ):
                validate_project(project_dir)

    def test_validate_project_calls_validate_entrypoint(self):
        """Test that validate_project calls validate_entrypoint for main.py."""
        with tempfile.TemporaryDirectory() as temp_dir:
            project_dir = Path(temp_dir)
            main_py = project_dir / "main.py"
            main_py.write_text("app = MCPApp()")

            with patch(
                "mcp_agent.cli.cloud.commands.deploy.validation.validate_entrypoint"
            ) as mock_validate:
                validate_project(project_dir)
                mock_validate.assert_called_once_with(main_py)


class TestValidateEntrypoint:
    """Tests for validate_entrypoint function."""

    def test_validate_entrypoint_success_simple(self):
        """Test validation of a simple valid entrypoint."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write("app = MCPApp(name='test-app')")
            f.flush()

            # Should not raise any exception
            validate_entrypoint(Path(f.name))

    def test_validate_entrypoint_success_multiline(self):
        """Test validation of a multiline MCPApp definition."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write("""
from mcp_agent.cloud import MCPApp

my_app = MCPApp(
    name="test-app",
    description="My test app"
)
""")
            f.flush()

            # Should not raise any exception
            validate_entrypoint(Path(f.name))

    def test_validate_entrypoint_success_with_variable_name(self):
        """Test validation with different variable names for MCPApp."""
        test_cases = [
            "app = MCPApp()",
            "my_app = MCPApp()",
            "agent = MCPApp()",
            "_private_app = MCPApp()",
            "app123 = MCPApp()",
        ]

        for content in test_cases:
            with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
                f.write(content)
                f.flush()

                # Should not raise any exception
                validate_entrypoint(Path(f.name))

    def test_validate_entrypoint_file_not_exists(self):
        """Test validation fails when entrypoint file doesn't exist."""
        non_existent_file = Path("/non/existent/file.py")

        with pytest.raises(
            FileNotFoundError, match="Entrypoint file .* does not exist"
        ):
            validate_entrypoint(non_existent_file)

    def test_validate_entrypoint_no_mcpapp_definition(self):
        """Test validation fails when no MCPApp definition is found."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write("""
import os
print("Hello world")

def main():
    pass
""")
            f.flush()

            with pytest.raises(
                ValueError, match="No MCPApp definition found in main.py"
            ):
                validate_entrypoint(Path(f.name))

    def test_validate_entrypoint_invalid_mcpapp_patterns(self):
        """Test validation fails for invalid MCPApp patterns."""
        invalid_patterns = [
            "# app = MCPApp()",  # commented out
            "MCPApp()",  # no assignment
            "print('app = MCPApp()')",  # in string
            "def create_app(): return MCPApp()",  # in function
        ]

        for content in invalid_patterns:
            with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
                f.write(content)
                f.flush()

                with pytest.raises(
                    ValueError, match="No MCPApp definition found in main.py"
                ):
                    validate_entrypoint(Path(f.name))

    @patch("mcp_agent.cli.cloud.commands.deploy.validation.print_warning")
    def test_validate_entrypoint_warns_about_main_block(self, mock_print_warning):
        """Test that validation warns about __main__ entrypoint."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write("""
app = MCPApp()

if __name__ == "__main__":
    app.run()
""")
            f.flush()

            # Should not raise exception but should warn
            validate_entrypoint(Path(f.name))
            mock_print_warning.assert_called_once_with(
                "Found a __main__ entrypoint in main.py. This will be ignored in the deployment."
            )

    @patch("mcp_agent.cli.cloud.commands.deploy.validation.print_warning")
    def test_validate_entrypoint_warns_about_main_block_variations(
        self, mock_print_warning
    ):
        """Test warning for different __main__ block variations."""
        main_block_variations = [
            'if __name__ == "__main__":\n    app.run()',
            "if __name__ == '__main__':\n    app.run()",
            'if __name__ == "__main__":\n    # comment\n    app.run()',
            'if __name__ == "__main__":\n    pass\n    app.run()\n    print("done")',
        ]

        for i, main_block in enumerate(main_block_variations):
            mock_print_warning.reset_mock()

            with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
                f.write(f"app = MCPApp()\n\n{main_block}")
                f.flush()

                validate_entrypoint(Path(f.name))
                mock_print_warning.assert_called_once()

    @patch("mcp_agent.cli.cloud.commands.deploy.validation.print_warning")
    def test_validate_entrypoint_no_warning_without_main_block(
        self, mock_print_warning
    ):
        """Test that no warning is issued when there's no __main__ block."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write("app = MCPApp()")
            f.flush()

            validate_entrypoint(Path(f.name))
            mock_print_warning.assert_not_called()

    def test_validate_entrypoint_with_complex_content(self):
        """Test validation with more complex but valid Python content."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write("""
import os
from pathlib import Path
from mcp_agent.cloud import MCPApp

# Configuration
CONFIG_PATH = Path(__file__).parent / "config.yaml"

def load_config():
    '''Load configuration from file.'''
    pass

# Create the MCP application
application = MCPApp(
    name="complex-app",
    config_path=CONFIG_PATH,
    debug=os.getenv("DEBUG", False)
)

class Helper:
    def __init__(self):
        pass
""")
            f.flush()

            # Should not raise any exception
            validate_entrypoint(Path(f.name))

    def test_validate_entrypoint_handles_encoding(self):
        """Test that validation handles different file encodings properly."""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False, encoding="utf-8"
        ) as f:
            f.write("""# -*- coding: utf-8 -*-
# This file contains unicode characters: test
app = MCPApp()
""")
            f.flush()

            # Should not raise any exception
            validate_entrypoint(Path(f.name))

    def test_validate_entrypoint_empty_file(self):
        """Test validation fails for empty files."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write("")
            f.flush()

            with pytest.raises(
                ValueError, match="No MCPApp definition found in main.py"
            ):
                validate_entrypoint(Path(f.name))
