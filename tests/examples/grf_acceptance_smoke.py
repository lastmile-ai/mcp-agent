"""Run a real GRF 0.6.1 failing-then-passing task lifecycle.

Usage: python tests/examples/grf_acceptance_smoke.py /grf-release
"""

import json
from pathlib import Path
import subprocess
import sys
import tempfile


def run(command, *, cwd, expect=0):
    result = subprocess.run(
        command, cwd=cwd, capture_output=True, text=True, check=False
    )
    if result.returncode != expect:
        raise AssertionError(
            f"{command!r} returned {result.returncode}, expected {expect}\n"
            f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        )
    return result


def main(runtime: Path) -> None:
    starter = runtime / "grf_starter.py"
    if not starter.is_file():
        raise FileNotFoundError(f"GRF release starter not found: {starter}")

    with tempfile.TemporaryDirectory(prefix="mcp-agent-grf-") as temp:
        project = Path(temp) / "agent project with spaces"
        intent = "Build and verify a small workflow deliverable"
        run(
            [sys.executable, str(starter), "init", str(project), "--intent", intent],
            cwd=Path(temp),
        )
        entry = project / "grf.py"

        def cli(*args, expect=0):
            return run([sys.executable, str(entry), *args], cwd=project, expect=expect)

        cli("session", "sign-in", "--task", intent)
        initial = json.loads(cli("session", "status").stdout)
        initial_id = initial["id"]
        assert initial["status"] == "active" and initial["completion"] is None

        # Generated acceptance intentionally fails; completion must not occur.
        failed = cli("check", expect=1)
        assert "FAIL" in (failed.stdout + failed.stderr)
        after_failure = json.loads(cli("session", "status").stdout)
        assert after_failure["id"] == initial_id
        assert after_failure["status"] == "active"
        assert after_failure["completion"] is None

        # Replace placeholder with real assertions against a generated artifact.
        (project / "deliverable.txt").write_text(
            "verified output\n", encoding="utf-8"
        )
        (project / "checks" / "acceptance.py").write_text(
            "from pathlib import Path\n"
            "assert Path('deliverable.txt').read_text(encoding='utf-8') == 'verified output\\n'\n",
            encoding="utf-8",
        )
        cli("check")
        evidence = project / "evidence.json"
        evidence.write_text(
            json.dumps({"artifact": "deliverable.txt", "verified": True}) + "\n",
            encoding="utf-8",
        )
        cli(
            "session",
            "complete",
            "--summary",
            "Implemented and verified the workflow deliverable",
            "--evidence",
            "deliverable.txt",
            "--evidence",
            "evidence.json",
        )
        finished = json.loads(cli("session", "status").stdout)
        assert finished["id"] == initial_id
        assert finished["completion"] is not None
        assert finished["completion"]["summary"] == (
            "Implemented and verified the workflow deliverable"
        )
        assert (project / "project.grf").is_file()
        assert (project / ".grf" / "session.json").is_file()
        assert (project / "deliverable.txt").read_text(encoding="utf-8") == "verified output\n"

    print("GRF real CLI failure/pass lifecycle smoke passed")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    main(Path(sys.argv[1]))
