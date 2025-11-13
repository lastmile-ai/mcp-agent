from __future__ import annotations

import copy
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class TraceEvent:
    timestamp: float
    event_type: str
    payload: Dict[str, Any]


@dataclass
class TraceRun:
    run_id: str
    workflow_id: Optional[str] = None
    workflow_name: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=lambda: time.time())
    events: List[TraceEvent] = field(default_factory=list)


class TraceStore:
    """In-memory store for per-run execution traces."""

    def __init__(self) -> None:
        self._runs: Dict[str, TraceRun] = {}
        self._lock = threading.Lock()

    def start_run(
        self,
        run_id: str,
        *,
        workflow_id: str | None = None,
        workflow_name: str | None = None,
        metadata: Dict[str, Any] | None = None,
    ) -> TraceRun:
        if not run_id:
            raise ValueError("run_id is required to start a trace")

        with self._lock:
            run = self._runs.get(run_id)
            if run is None:
                run = TraceRun(
                    run_id=run_id,
                    workflow_id=workflow_id,
                    workflow_name=workflow_name,
                    metadata=metadata or {},
                )
                self._runs[run_id] = run
            else:
                if workflow_id:
                    run.workflow_id = workflow_id
                if workflow_name:
                    run.workflow_name = workflow_name
                if metadata:
                    run.metadata.update(metadata)
            return copy.deepcopy(run)

    def append_event(
        self,
        run_id: str,
        event_type: str,
        payload: Dict[str, Any],
        *,
        timestamp: float | None = None,
    ) -> None:
        if not run_id:
            return

        event = TraceEvent(
            timestamp=timestamp or time.time(),
            event_type=event_type,
            payload=copy.deepcopy(payload),
        )

        with self._lock:
            run = self._runs.setdefault(run_id, TraceRun(run_id=run_id))
            run.events.append(event)

    def get_run(self, run_id: str) -> Optional[TraceRun]:
        with self._lock:
            run = self._runs.get(run_id)
            if run is None:
                return None
            return copy.deepcopy(run)

    def list_runs(self) -> List[TraceRun]:
        with self._lock:
            return [copy.deepcopy(run) for run in self._runs.values()]

    def clear(self, run_id: str | None = None) -> None:
        with self._lock:
            if run_id is None:
                self._runs.clear()
            else:
                self._runs.pop(run_id, None)
