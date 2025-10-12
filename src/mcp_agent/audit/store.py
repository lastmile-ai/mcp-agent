"""Append-only audit trail persistence utilities."""

from __future__ import annotations

import json
import os
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, Literal


AllowedActor = Literal["system", "studio", "sentinel"]


@dataclass(slots=True)
class AuditRecord:
    ts: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    run_id: str = ""
    trace_id: str = ""
    actor: AllowedActor = "system"
    action: str = ""
    target: str | None = None
    params_hash: str | None = None
    outcome: str | None = None
    error_code: str | None = None

    def to_json(self) -> Dict[str, Any]:
        self._validate()
        return {
            "ts": self.ts.isoformat(),
            "run_id": self.run_id,
            "trace_id": self.trace_id,
            "actor": self.actor,
            "action": self.action,
            "target": self.target,
            "params_hash": self.params_hash,
            "outcome": self.outcome,
            "error_code": self.error_code,
        }

    def _validate(self) -> None:
        if not self.run_id:
            raise ValueError("run_id is required for audit records")
        if not self.trace_id:
            raise ValueError("trace_id is required for audit records")
        if self.actor not in {"system", "studio", "sentinel"}:
            raise ValueError(f"unsupported_actor:{self.actor}")
        if not self.action:
            raise ValueError("action is required for audit records")


class AuditStore:
    """Simple append-only audit file store."""

    def __init__(self, root: str | Path | None = None, enabled: bool | None = None) -> None:
        self._root = Path(root or os.getenv("ARTIFACTS_ROOT", "./artifacts")).resolve()
        self._enabled = bool(os.getenv("AUDIT_ENABLED", "true").lower() != "false") if enabled is None else enabled
        self._root.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    @property
    def enabled(self) -> bool:
        return self._enabled

    def _run_dir(self, run_id: str) -> Path:
        return self._root / run_id

    def write(self, record: AuditRecord) -> Path:
        if not self.enabled:
            raise RuntimeError("audit_disabled")
        payload = record.to_json()
        run_dir = self._run_dir(record.run_id)
        audit_path = run_dir / "audit.ndjson"

        with self._lock:
            run_dir.mkdir(parents=True, exist_ok=True)
            with audit_path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(payload, separators=(",", ":")))
                fh.write("\n")
            os.chmod(audit_path, 0o640)
        return audit_path

    def iter_records(self, run_id: str) -> Iterable[Dict[str, Any]]:
        path = self._run_dir(run_id) / "audit.ndjson"
        if not path.exists():
            return []
        with path.open("r", encoding="utf-8") as fh:
            return [json.loads(line) for line in fh if line.strip()]


__all__ = ["AuditRecord", "AuditStore"]

