import re
from pathlib import Path

from mcp_agent.cli.ux import print_warning


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
