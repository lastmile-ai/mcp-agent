"""Base implementation for executing test commands and managing artifacts."""

from __future__ import annotations

import json
import os
import subprocess
import time
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Dict, Iterable, List, Mapping, MutableMapping, Tuple

from mcp_agent.artifacts.index import ArtifactIndex

from .junit import junit_sha256, parse_or_synthesise_junit
from .result import TestRunnerResult
from .spec import TestRunnerConfig, TestRunnerSpec
from .telemetry import TestRunTelemetry


class TestRunner(ABC):
    language: str

    def __init__(self, *, artifact_index: ArtifactIndex | None = None, telemetry: TestRunTelemetry | None = None) -> None:
        self.artifact_index = artifact_index or ArtifactIndex()
        self.telemetry = telemetry or TestRunTelemetry()

    @abstractmethod
    def defaults(self, spec: TestRunnerSpec) -> TestRunnerSpec:
        """Return default values for the spec (commands, junit path, etc)."""

    def execute(self, spec: TestRunnerSpec, config: TestRunnerConfig) -> TestRunnerResult:
        resolved = spec.merge(self.defaults(spec))
        language = resolved.language or self.language
        if language is None:
            raise ValueError("language_not_set")
        commands = resolved.resolved_commands()
        if not commands:
            raise ValueError("no_commands_configured")
        run_id = config.run_id or _default_run_id()
        env = os.environ.copy()
        if resolved.env:
            env.update(resolved.env)
        stdout_chunks: List[str] = []
        stderr_chunks: List[str] = []
        last_exit_code = 0
        start = time.perf_counter()
        cwd = (resolved.project_root or config.project_root or Path.cwd()).resolve()
        junit_path = resolved.junit_path
        if junit_path is not None and not junit_path.is_absolute():
            junit_path = (cwd / junit_path).resolve()
        for command in commands:
            try:
                completed = subprocess.run(
                    command,
                    cwd=str(cwd),
                    env=env,
                    capture_output=True,
                    text=True,
                    timeout=resolved.timeout,
                    check=False,
                )
            except subprocess.TimeoutExpired as exc:
                stdout_chunks.append(exc.stdout or "")
                stderr_chunks.append(exc.stderr or "")
                last_exit_code = -1
                break
            stdout_chunks.append(completed.stdout)
            stderr_chunks.append(completed.stderr)
            last_exit_code = completed.returncode
            if completed.returncode != 0:
                break
        duration = time.perf_counter() - start
        stdout = "".join(stdout_chunks)
        stderr = "".join(stderr_chunks)
        junit_xml, normalized = parse_or_synthesise_junit(junit_path, stdout, stderr, last_exit_code)
        artifacts = self._persist_artifacts(
            run_id,
            stdout,
            stderr,
            junit_xml,
            language,
            commands[-1],
            duration,
            last_exit_code,
            cwd,
            junit_path,
        )
        result = TestRunnerResult(
            language=language,
            run_id=run_id,
            exit_code=last_exit_code,
            duration=duration,
            stdout=stdout,
            stderr=stderr,
            junit_xml=junit_xml,
            normalized=normalized,
            artifacts=artifacts,
            command=list(commands[-1]),
        )
        self.telemetry.emit_event(
            runner=language,
            result="success" if result.succeeded else "failure",
            duration=duration,
            exit_code=last_exit_code,
            artifacts=artifacts,
            junit_hash=junit_sha256(junit_xml),
            extra=config.telemetry_attributes,
        )
        return result

    def _persist_artifacts(
        self,
        run_id: str,
        stdout: str,
        stderr: str,
        junit_xml: str,
        language: str,
        command: Iterable[str],
        duration: float,
        exit_code: int,
        cwd: Path,
        junit_path: Path | None,
    ) -> Mapping[str, str]:
        index = self.artifact_index
        index.ensure_dir(run_id)
        stored: Dict[str, str] = {}
        stdout_path = index.persist_bytes(run_id, "test-stdout.log", stdout.encode("utf-8"), media_type="text/plain")
        stored["stdout"] = stdout_path.name
        stderr_path = index.persist_bytes(run_id, "test-stderr.log", stderr.encode("utf-8"), media_type="text/plain")
        stored["stderr"] = stderr_path.name
        junit_path_disk = index.persist_bytes(run_id, "test-junit.xml", junit_xml.encode("utf-8"), media_type="application/xml")
        stored["junit"] = junit_path_disk.name
        meta = {
            "language": language,
            "command": list(command),
            "duration_seconds": duration,
            "exit_code": exit_code,
            "cwd": str(cwd),
            "junit_source": str(junit_path) if junit_path else None,
        }
        meta_path = index.persist_bytes(run_id, "test-meta.json", json.dumps(meta, indent=2).encode("utf-8"), media_type="application/json")
        stored["meta"] = meta_path.name
        return stored


def _default_run_id() -> str:
    import uuid

    return uuid.uuid4().hex


__all__ = ["TestRunner"]
