"""Shared utilities for working with artifact files."""

from __future__ import annotations

import hashlib
from pathlib import Path


def sha256_digest(path: Path) -> str:
    """Compute the SHA256 digest for a file."""

    hasher = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(8192), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


__all__ = ["sha256_digest"]

