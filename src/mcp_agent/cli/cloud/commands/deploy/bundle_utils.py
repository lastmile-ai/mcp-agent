"""Utilities for enhancing bundle process with gitignore support and comment cleaning."""

import ast
from pathlib import Path
from typing import Optional, Set
import pathspec
import yaml


def create_pathspec_from_gitignore(gitignore_path: Path) -> Optional[pathspec.PathSpec]:
    """Create a PathSpec object from a .gitignore file.

    Args:
        gitignore_path: Path to the .gitignore file

    Returns:
        PathSpec object for matching paths, or None if file doesn't exist
    """
    if not gitignore_path.exists():
        return None

    with open(gitignore_path, 'r') as f:
        spec = pathspec.PathSpec.from_lines('gitwildmatch', f)

    return spec


def create_gitignore_matcher(project_dir: Path) -> callable:
    """Create a matcher function for gitignore patterns.

    Args:
        project_dir: The project directory containing .gitignore

    Returns:
        A function that checks if a path should be ignored
    """
    gitignore_path = project_dir / '.gitignore'
    spec = create_pathspec_from_gitignore(gitignore_path)

    def should_ignore(path: Path, name: str) -> bool:
        """Check if a file/dir should be ignored based on gitignore.

        Args:
            path: Full path to the file or directory
            name: Name of the file or directory

        Returns:
            True if should be ignored
        """
        if spec is None:
            return False

        # Get relative path from project directory
        try:
            rel_path = path.relative_to(project_dir)
        except ValueError:
            # If path is not relative to project_dir, don't ignore
            return False

        # Check if path matches gitignore patterns
        # PathSpec.match_file expects a string path
        return spec.match_file(str(rel_path))

    return should_ignore


def should_ignore_by_gitignore(path_str: str, names: list, project_dir: Path, spec: Optional[pathspec.PathSpec]) -> Set[str]:
    """Determine which names should be ignored based on gitignore patterns.

    This function is designed to work with shutil.copytree's ignore parameter.

    Args:
        path_str: Current directory path being processed (as string)
        names: List of names in the current directory
        project_dir: The project root directory
        spec: PathSpec object with gitignore patterns, or None

    Returns:
        Set of names that should be ignored
    """
    if spec is None:
        return set()

    ignored = set()
    current_path = Path(path_str)

    for name in names:
        full_path = current_path / name
        try:
            # Get path relative to project directory
            rel_path = full_path.relative_to(project_dir)
            rel_path_str = str(rel_path)

            # Check if this path matches gitignore patterns
            # For directories, also check with trailing slash
            if spec.match_file(rel_path_str):
                ignored.add(name)
            elif full_path.is_dir() and spec.match_file(rel_path_str + '/'):
                ignored.add(name)
        except ValueError:
            # Path is not relative to project_dir, don't ignore
            continue

    return ignored


def clean_yaml_comments(yaml_content: str) -> str:
    """Remove comments from YAML content while preserving structure.

    Args:
        yaml_content: The YAML content as a string

    Returns:
        The YAML content without comments
    """
    try:
        # Parse the YAML content
        data = yaml.safe_load(yaml_content)

        # Dump it back without comments
        cleaned = yaml.dump(data, default_flow_style=False, sort_keys=False, allow_unicode=True)

        return cleaned
    except yaml.YAMLError:
        # If parsing fails, return original content
        return yaml_content


def clean_python_comments(python_content: str) -> str:
    """Remove comments and docstrings from Python code while preserving functionality.

    Args:
        python_content: The Python code as a string

    Returns:
        The Python code without comments and docstrings
    """
    try:
        # Parse the Python code into an AST
        tree = ast.parse(python_content)

        # Remove docstrings by replacing them with pass statements
        class DocstringRemover(ast.NodeTransformer):
            def visit_FunctionDef(self, node):
                # Remove docstring if it exists
                if (node.body and
                    isinstance(node.body[0], ast.Expr) and
                    isinstance(node.body[0].value, (ast.Str, ast.Constant))):
                    node.body.pop(0)
                    # Add pass if body is now empty
                    if not node.body:
                        node.body.append(ast.Pass())
                self.generic_visit(node)
                return node

            def visit_AsyncFunctionDef(self, node):
                # Same logic for async functions
                if (node.body and
                    isinstance(node.body[0], ast.Expr) and
                    isinstance(node.body[0].value, (ast.Str, ast.Constant))):
                    node.body.pop(0)
                    if not node.body:
                        node.body.append(ast.Pass())
                self.generic_visit(node)
                return node

            def visit_ClassDef(self, node):
                # Remove class docstring
                if (node.body and
                    isinstance(node.body[0], ast.Expr) and
                    isinstance(node.body[0].value, (ast.Str, ast.Constant))):
                    node.body.pop(0)
                    if not node.body:
                        node.body.append(ast.Pass())
                self.generic_visit(node)
                return node

            def visit_Module(self, node):
                # Remove module docstring
                if (node.body and
                    isinstance(node.body[0], ast.Expr) and
                    isinstance(node.body[0].value, (ast.Str, ast.Constant))):
                    node.body.pop(0)
                self.generic_visit(node)
                return node

        transformer = DocstringRemover()
        tree = transformer.visit(tree)

        # Compile back to code
        cleaned_code = ast.unparse(tree)

        # Now remove inline comments (lines starting with #)
        lines = []
        for line in cleaned_code.split('\n'):
            # Remove lines that are only comments
            stripped = line.lstrip()
            if stripped and not stripped.startswith('#'):
                # Remove inline comments from the line
                # Find # not inside strings
                in_string = False
                string_char = None
                cleaned_line = []
                i = 0
                while i < len(line):
                    char = line[i]

                    # Handle string boundaries
                    if char in ('"', "'") and (i == 0 or line[i-1] != '\\'):
                        if not in_string:
                            in_string = True
                            string_char = char
                        elif char == string_char:
                            in_string = False

                    # If we find # outside a string, truncate here
                    if char == '#' and not in_string:
                        # Remove trailing whitespace
                        result = ''.join(cleaned_line).rstrip()
                        if result:  # Only add non-empty lines
                            lines.append(result)
                        break

                    cleaned_line.append(char)
                    i += 1
                else:
                    # No comment found, add the whole line if non-empty
                    if line.strip():
                        lines.append(line.rstrip())

        return '\n'.join(lines)

    except SyntaxError:
        # If parsing fails, at least try to remove simple comments
        lines = []
        for line in python_content.split('\n'):
            stripped = line.lstrip()
            if stripped and not stripped.startswith('#'):
                # Try to remove inline comments (basic approach)
                if '#' in line:
                    # Find first # not in a string (simple heuristic)
                    parts = line.split('#')
                    if parts[0].strip():
                        lines.append(parts[0].rstrip())
                else:
                    lines.append(line.rstrip())
            elif not stripped.startswith('#'):
                # Keep empty lines for structure
                lines.append('')
        return '\n'.join(lines)


def clean_yaml_files_in_directory(directory: Path) -> int:
    """Clean comments from all YAML files in a directory tree.

    Args:
        directory: Root directory to process

    Returns:
        Number of files cleaned
    """
    cleaned_count = 0

    for yaml_path in directory.rglob("*.yaml"):
        try:
            with open(yaml_path, 'r', encoding='utf-8') as f:
                original_content = f.read()

            cleaned_content = clean_yaml_comments(original_content)

            # Only write back if content actually changed
            if cleaned_content != original_content:
                with open(yaml_path, 'w', encoding='utf-8') as f:
                    f.write(cleaned_content)
                cleaned_count += 1

        except Exception:
            # Skip files that can't be processed
            continue

    # Also process .yml files
    for yml_path in directory.rglob("*.yml"):
        try:
            with open(yml_path, 'r', encoding='utf-8') as f:
                original_content = f.read()

            cleaned_content = clean_yaml_comments(original_content)

            if cleaned_content != original_content:
                with open(yml_path, 'w', encoding='utf-8') as f:
                    f.write(cleaned_content)
                cleaned_count += 1

        except Exception:
            continue

    return cleaned_count


def clean_python_files_in_directory(directory: Path) -> int:
    """Clean comments and docstrings from all Python files in a directory tree.

    Args:
        directory: Root directory to process

    Returns:
        Number of files cleaned
    """
    cleaned_count = 0

    for py_path in directory.rglob("*.py"):
        try:
            with open(py_path, 'r', encoding='utf-8') as f:
                original_content = f.read()

            cleaned_content = clean_python_comments(original_content)

            # Only write back if content actually changed
            if cleaned_content != original_content:
                with open(py_path, 'w', encoding='utf-8') as f:
                    f.write(cleaned_content)
                cleaned_count += 1

        except Exception:
            # Skip files that can't be processed
            continue

    return cleaned_count