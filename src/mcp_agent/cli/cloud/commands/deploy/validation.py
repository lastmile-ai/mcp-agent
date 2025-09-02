import os
import re
from pathlib import Path

from mcp_agent.cli.utils.ux import print_warning


def validate_project(project_dir: Path):
    """
    Validates the project directory structure and required files.
    Raises an exception if validation fails.
    Logs warnings for non-critical issues.
    """
    if not project_dir.exists():
        raise FileNotFoundError(f"Project directory {project_dir} does not exist.")

    required_files = ["main.py"]
    for file in required_files:
        if not (project_dir / file).exists():
            raise FileNotFoundError(
                f"Required file {file} is missing in the project directory."
            )

    validate_entrypoint(project_dir / "main.py")

    has_requirements = os.path.exists(os.path.join(project_dir, "requirements.txt"))
    has_poetry_lock = os.path.exists(os.path.join(project_dir, "poetry.lock"))
    has_uv_lock = os.path.exists(os.path.join(project_dir, "uv.lock"))

    # Make sure only one python project dependency management is used
    # pyproject.toml is allowed alongside lock/requirements files
    if sum([has_requirements, has_poetry_lock, has_uv_lock]) > 1:
        raise ValueError(
            "Multiple Python project dependency management files found. Expected only one of: requirements.txt, poetry.lock, uv.lock"
        )

    has_pyproject = os.path.exists(os.path.join(project_dir, "pyproject.toml"))
    if has_uv_lock and not has_pyproject:
        raise ValueError(
            "Invalid uv project: uv.lock found without corresponding pyproject.toml"
        )
    if has_poetry_lock and not has_pyproject:
        raise ValueError(
            "Invalid poetry project: poetry.lock found without corresponding pyproject.toml"
        )


def validate_entrypoint(entrypoint_path: Path):
    """
    Validates the entrypoint file for the project.
    Raises an exception if the contents are not valid.
    """
    if not entrypoint_path.exists():
        raise FileNotFoundError(f"Entrypoint file {entrypoint_path} does not exist.")

    with open(entrypoint_path, "r", encoding="utf-8") as f:
        content = f.read()

        # Matches any assignment to MCPApp(...) including multiline calls
        has_app_def = re.search(r"^(\w+)\s*=\s*MCPApp\s*\(", content, re.MULTILINE)
        if not has_app_def:
            raise ValueError("No MCPApp definition found in main.py.")

        # Warn if there is a __main__ entrypoint (will be ignored)
        has_main = re.search(
            r'(?m)^if\s+__name__\s*==\s*[\'"]__main__[\'"]\s*:\n(?:[ \t]+.*\n?)*',
            content,
        )

        if has_main:
            print_warning(
                "Found a __main__ entrypoint in main.py. This will be ignored in the deployment."
            )
