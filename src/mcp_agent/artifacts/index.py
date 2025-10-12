"""Helpers for managing persisted run artifacts."""

from __future__ import annotations

import json
import mimetypes
import os
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Optional

from .utils import sha256_digest


@dataclass(slots=True)
class ArtifactEntry:
    name: str
    size: int
    sha256: str
    media_type: str
    updated_at: str


class ArtifactIndex:
    """Builds canonical indexes for run artifacts."""

    def __init__(self, root: str | Path | None = None) -> None:
        self._root = Path(root or os.getenv("ARTIFACTS_ROOT", "./artifacts")).resolve()
        self._root.mkdir(parents=True, exist_ok=True)

    def run_dir(self, run_id: str) -> Path:
        path = (self._root / run_id).resolve()
        if self._root not in path.parents and path != self._root:
            raise ValueError("invalid_run_id")
        return path

    def ensure_dir(self, run_id: str) -> Path:
        path = self.run_dir(run_id)
        path.mkdir(parents=True, exist_ok=True)
        return path

    def persist_bytes(self, run_id: str, name: str, data: bytes, *, media_type: str = "application/octet-stream") -> Path:
        target = self.ensure_dir(run_id) / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        os.chmod(target, 0o640)
        meta_path = target.with_suffix(target.suffix + ".meta.json")
        meta_path.write_text(json.dumps({"media_type": media_type}), encoding="utf-8")
        os.chmod(meta_path, 0o640)
        return target

    def list_entries(self, run_id: str) -> List[ArtifactEntry]:
        run_dir = self.run_dir(run_id)
        if not run_dir.exists():
            return []
        entries: List[ArtifactEntry] = []
        for path in sorted(run_dir.rglob("*")):
            if path.is_dir() or path.suffix == ".meta.json":
                continue
            rel = path.relative_to(run_dir).as_posix()
            stat = path.stat()
            media_type = self._resolve_media_type(path)
            entries.append(
                ArtifactEntry(
                    name=rel,
                    size=stat.st_size,
                    sha256=sha256_digest(path),
                    media_type=media_type,
                    updated_at=datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(),
                )
            )
        return entries

    def build_index(self, run_id: str) -> Dict[str, object]:
        return {
            "run_id": run_id,
            "artifacts": [asdict(entry) for entry in self.list_entries(run_id)],
        }

    def get_artifact(self, run_id: str, name: str) -> tuple[bytes, str]:
        path = (self.run_dir(run_id) / name).resolve()
        if not path.exists() or not path.is_file():
            raise FileNotFoundError(name)
        if self._root not in path.parents and path != self._root:
            raise ValueError("invalid_path")
        media_type = self._resolve_media_type(path)
        return path.read_bytes(), media_type

    def _resolve_media_type(self, path: Path) -> str:
        meta_path = path.with_suffix(path.suffix + ".meta.json")
        if meta_path.exists():
            try:
                payload = json.loads(meta_path.read_text(encoding="utf-8"))
                media_type = payload.get("media_type")
                if isinstance(media_type, str):
                    return media_type
            except Exception:
                pass
        guess, _ = mimetypes.guess_type(path.name)
        return guess or "application/octet-stream"


__all__ = ["ArtifactEntry", "ArtifactIndex"]

