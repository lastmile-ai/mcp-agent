"""Ignore-file helpers for the deploy bundler.

This module focuses on two things:
- Parse an ignore file (gitignore-compatible syntax) into a `PathSpec` matcher.
- Provide an adapter that works with `shutil.copytree(ignore=...)` to decide
  which directory entries to skip during a copy.

There is no implicit reading of `.gitignore` here. Callers must explicitly
pass the ignore file path they want to use (e.g., `.mcpacignore`).
"""

from pathlib import Path
from typing import Optional, Set
import pathspec


def create_pathspec_from_gitignore(
    ignore_file_path: Path,
) -> Optional[pathspec.PathSpec]:
    """Create and return a `PathSpec` from an ignore file.

    The file is parsed using the `gitwildmatch` (gitignore) syntax. If the file
    does not exist, `None` is returned so callers can fall back to default
    behavior.

    Args:
        ignore_file_path: Path to the ignore file (e.g., `.mcpacignore`).

    Returns:
        A `PathSpec` that can match file/directory paths, or `None`.
    """
    if not ignore_file_path.exists():
        return None

    with open(ignore_file_path, "r", encoding="utf-8") as f:
        spec = pathspec.PathSpec.from_lines("gitwildmatch", f)

    return spec


def should_ignore_by_gitignore(
    path_str: str, names: list, project_dir: Path, spec: Optional[pathspec.PathSpec]
) -> Set[str]:
    """Return the subset of `names` to ignore for `shutil.copytree`.

    This function is designed to be passed as the `ignore` callback to
    `shutil.copytree`. For each entry in the current directory (`path_str`), it
    computes the path relative to the `project_dir` root and checks it against
    the provided `spec` (a `PathSpec` created from an ignore file).

    Notes:
    - If `spec` is `None`, this returns an empty set (no additional ignores).
    - For directories, we also check the relative path with a trailing slash
      (a common gitignore convention).
    """
    if spec is None:
        return set()

    ignored: Set[str] = set()
    current_path = Path(path_str)

    for name in names:
        full_path = current_path / name
        try:
            rel_path = full_path.relative_to(project_dir)
        except ValueError:
            # If `full_path` is not under `project_dir`, ignore matching is skipped.
            continue

        # Normalize to POSIX separators so patterns work cross-platform (Windows too)
        rel_path_str = rel_path.as_posix()

        # Match files exactly; for directories also try with a trailing slash
        # to respect patterns like `build/`.
        if spec.match_file(rel_path_str):
            ignored.add(name)
        elif full_path.is_dir() and spec.match_file(rel_path_str + "/"):
            ignored.add(name)

    return ignored
