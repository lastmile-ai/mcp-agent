"""Utility for reading optional test index metadata."""

from __future__ import annotations

from pathlib import Path
from typing import Iterable, List


def read_index(path: str | Path) -> List[str]:
    p = Path(path)
    if not p.exists():
        return []
    return [line.strip() for line in p.read_text().splitlines() if line.strip()]


def expand_tests(changed_paths: Iterable[str], index: list[str]) -> List[str]:
    if not index:
        return list(changed_paths)
    # naive mapping: return index entries that start with changed path
    expanded: List[str] = []
    for entry in index:
        for changed in changed_paths:
            if entry.startswith(changed):
                expanded.append(entry)
                break
    return expanded or list(changed_paths)


__all__ = ["read_index", "expand_tests"]
