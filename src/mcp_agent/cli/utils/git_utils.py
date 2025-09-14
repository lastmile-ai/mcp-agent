"""Lightweight git helpers for deployment metadata and tagging.

These helpers avoid third-party dependencies and use subprocess to query git.
All functions are safe to call outside a git repo (they return None/fallbacks).
"""

from __future__ import annotations

import hashlib
import os
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


@dataclass
class GitMetadata:
    """Key git details about the working copy to embed with deployments."""

    commit_sha: str
    short_sha: str
    branch: Optional[str]
    dirty: bool
    tag: Optional[str]
    commit_message: Optional[str]


def _run_git(args: list[str], cwd: Path) -> Optional[str]:
    try:
        out = subprocess.check_output(["git", *args], cwd=str(cwd))
        return out.decode("utf-8", errors="replace").strip()
    except Exception:
        return None


def get_git_metadata(project_dir: Path) -> Optional[GitMetadata]:
    """Return GitMetadata for the repo containing project_dir, if any.

    Returns None if git is unavailable or project_dir is not inside a repo.
    """
    # Fast probe: are we inside a work-tree?
    inside = _run_git(["rev-parse", "--is-inside-work-tree"], project_dir)
    if inside is None or inside != "true":
        return None

    commit_sha = _run_git(["rev-parse", "HEAD"], project_dir)
    if not commit_sha:
        return None

    short_sha = (
        _run_git(["rev-parse", "--short", "HEAD"], project_dir) or commit_sha[:7]
    )
    branch = _run_git(["rev-parse", "--abbrev-ref", "HEAD"], project_dir)
    status = _run_git(["status", "--porcelain"], project_dir)
    dirty = bool(status)
    tag = _run_git(["describe", "--tags", "--exact-match"], project_dir)
    commit_message = _run_git(["log", "-1", "--pretty=%s"], project_dir)

    return GitMetadata(
        commit_sha=commit_sha,
        short_sha=short_sha,
        branch=branch,
        dirty=dirty,
        tag=tag,
        commit_message=commit_message,
    )


def utc_iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def compute_directory_hash(root: Path, *, ignore_names: set[str] | None = None) -> str:
    """Compute SHA256 over file names and contents under root.

    NOTE: This reads file contents and can be expensive for very large trees.
    Prefer `compute_directory_fingerprint` below for fast fingerprints.
    """
    if ignore_names is None:
        ignore_names = set()

    h = hashlib.sha256()
    for dirpath, dirnames, filenames in os.walk(root):
        # Filter dirnames in-place to prune traversal
        dirnames[:] = [
            d for d in dirnames if d not in ignore_names and not d.startswith(".")
        ]
        for fname in sorted(filenames):
            if fname in ignore_names or fname.startswith("."):
                # Allow .env explicitly
                if fname == ".env":
                    pass
                else:
                    continue
            fpath = Path(dirpath) / fname
            if fpath.is_symlink():
                continue
            rel = fpath.relative_to(root).as_posix()
            try:
                with open(fpath, "rb") as f:
                    data = f.read()
            except Exception:
                data = b""
            h.update(rel.encode("utf-8"))
            h.update(b"\0")
            h.update(data)
            h.update(b"\n")
    return h.hexdigest()


def compute_directory_fingerprint(
    root: Path, *, ignore_names: set[str] | None = None
) -> str:
    """Compute a cheap, stable SHA256 over file metadata under root.

    This avoids reading file contents. The hash includes the relative path,
    file size and modification time for each included file. Hidden files/dirs
    and any names in `ignore_names` are skipped, as are symlinks.
    """
    if ignore_names is None:
        ignore_names = set()

    h = hashlib.sha256()
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [
            d for d in dirnames if d not in ignore_names and not d.startswith(".")
        ]
        for fname in sorted(filenames):
            if fname in ignore_names or (fname.startswith(".") and fname != ".env"):
                continue
            fpath = Path(dirpath) / fname
            if fpath.is_symlink():
                continue
            rel = fpath.relative_to(root).as_posix()
            try:
                st = fpath.stat()
                size = st.st_size
                mtime = int(st.st_mtime)
            except Exception:
                size = -1
                mtime = 0
            h.update(rel.encode("utf-8"))
            h.update(b"\0")
            h.update(str(size).encode("utf-8"))
            h.update(b"\0")
            h.update(str(mtime).encode("utf-8"))
            h.update(b"\n")
    return h.hexdigest()


def create_git_tag(project_dir: Path, tag_name: str, message: str) -> bool:
    """Create an annotated git tag at HEAD. Returns True on success.

    Does nothing and returns False if not a repo or git fails.
    """
    inside = _run_git(["rev-parse", "--is-inside-work-tree"], project_dir)
    if inside is None or inside != "true":
        return False
    try:
        subprocess.check_call(
            ["git", "tag", "-a", tag_name, "-m", message], cwd=str(project_dir)
        )
        return True
    except Exception:
        return False
