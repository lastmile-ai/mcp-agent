from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from examples.usecases.grf_acceptance import grf_gate


class GrfGateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.project = Path(self.temp.name)
        self.entrypoint = self.project / "grf.py"
        self.entrypoint.touch()

    @patch("examples.usecases.grf_acceptance.grf_gate.subprocess.run")
    def test_start_uses_argv_and_original_project_working_directory(self, run):
        run.return_value = subprocess.CompletedProcess([], 0, "started", "")
        result = grf_gate.start_grf_task(
            self.project, "Implement useful workflow behavior"
        )

        self.assertEqual(result["stdout"], "started")
        self.assertEqual(
            run.call_args.args[0],
            [
                sys.executable,
                str(self.entrypoint.resolve()),
                "session",
                "sign-in",
                "--task",
                "Implement useful workflow behavior",
            ],
        )
        self.assertEqual(run.call_args.kwargs["cwd"], self.project.resolve())
        self.assertFalse(run.call_args.kwargs["check"])

    @patch("examples.usecases.grf_acceptance.grf_gate.subprocess.run")
    def test_complete_passes_summary_and_evidence_as_separate_arguments(self, run):
        run.return_value = subprocess.CompletedProcess([], 0, "completed", "")
        grf_gate.complete_grf_task(
            self.project,
            "Implemented the requested workflow feature",
            ["outputs/result.json", "logs/check.txt"],
        )

        self.assertEqual(
            run.call_args.args[0],
            [
                sys.executable,
                str(self.entrypoint.resolve()),
                "session",
                "complete",
                "--summary",
                "Implemented the requested workflow feature",
                "--evidence",
                "outputs/result.json",
                "--evidence",
                "logs/check.txt",
            ],
        )

    @patch("examples.usecases.grf_acceptance.grf_gate.subprocess.run")
    def test_failed_acceptance_is_not_swallowed(self, run):
        run.return_value = subprocess.CompletedProcess(
            [], 1, "stdout detail", "exact failed check"
        )
        with self.assertRaisesRegex(RuntimeError, "exact failed check"):
            grf_gate.complete_grf_task(
                self.project, "Finished a meaningful workflow task", ["result.txt"]
            )

    def test_invalid_inputs_and_missing_project_entrypoint(self):
        with self.assertRaisesRegex(ValueError, "concrete task"):
            grf_gate.start_grf_task(self.project, "short")
        self.entrypoint.unlink()
        with self.assertRaisesRegex(FileNotFoundError, "project-local GRF entrypoint"):
            grf_gate.complete_grf_task(
                self.project, "Finished a meaningful workflow task", ["result.txt"]
            )
        self.entrypoint.touch()
        with self.assertRaisesRegex(ValueError, "evidence"):
            grf_gate.complete_grf_task(self.project, "Completed meaningful work", [])


if __name__ == "__main__":
    unittest.main()
