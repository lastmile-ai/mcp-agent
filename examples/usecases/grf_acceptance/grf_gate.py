"""Small opt-in bridge from an mcp-agent workflow to a local GRF project."""

from pathlib import Path
import subprocess
import sys
from collections.abc import Sequence


def _grf(project: Path, *args: str) -> dict:
    root = project.expanduser().resolve()
    entrypoint = root / "grf.py"
    if not entrypoint.is_file():
        raise FileNotFoundError(
            f"No project-local GRF entrypoint at {entrypoint}; initialize this project with GRF first."
        )
    command = [sys.executable, str(entrypoint), *args]
    result = subprocess.run(
        command,
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode:
        detail = (result.stderr or result.stdout).strip()
        raise RuntimeError(
            f"GRF command failed ({result.returncode}): {command!r}"
            + (f"\n{detail}" if detail else "")
        )
    return {"stdout": result.stdout, "stderr": result.stderr}


def start_grf_task(project: Path, task: str) -> dict:
    """Sign in to a concrete GRF task before starting the workflow."""
    if len(task.strip()) < 10:
        raise ValueError("Provide a concrete task of at least 10 characters")
    return _grf(project, "session", "sign-in", "--task", task)


def complete_grf_task(
    project: Path, summary: str, evidence: Sequence[str]
) -> dict:
    """Complete only after GRF's fresh acceptance run and evidence checks pass.

    Call this immediately before returning a successful WorkflowResult. A
    nonzero GRF result raises, so mcp-agent records the workflow as an error
    instead of reporting normal completion. The GRF task remains active for
    repair/resume; this helper never edits GRF session files.
    """
    if len(summary.strip()) < 10:
        raise ValueError("Provide a meaningful completion summary")
    if not evidence:
        raise ValueError("At least one project-relative evidence file is required")
    return _grf(
        project,
        "session",
        "complete",
        "--summary",
        summary,
        *[argument for path in evidence for argument in ("--evidence", path)],
    )
