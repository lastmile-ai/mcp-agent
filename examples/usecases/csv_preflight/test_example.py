"""Run with python -m unittest -v from this example directory."""

import asyncio
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from main import EXAMPLE_DIR, check_csv, make_app
from validator import MAX_CHARS, validate_csv

from mcp_agent.agents.agent import Agent

HEADER = "invoice_id,amount,invoice_date\n"


class ValidationTests(unittest.TestCase):
    def test_valid_fixture_and_credit(self):
        report = validate_csv((EXAMPLE_DIR / "valid.csv").read_text())
        self.assertTrue(report["ok"])
        self.assertEqual(report["rows_read"], 2)
        self.assertEqual(report["errors"], [])

    def test_invalid_fixture_reports_all_three_problems(self):
        report = validate_csv((EXAMPLE_DIR / "invalid.csv").read_text())
        self.assertFalse(report["ok"])
        self.assertEqual(
            [e["field"] for e in report["errors"]],
            ["invoice_id", "amount", "invoice_date"],
        )
        self.assertEqual({e["record"] for e in report["errors"]}, {3})

    def test_decimal_and_calendar_edges(self):
        for amount in ("NaN", "sNaN", "Infinity", "-Infinity", "", "1.2.3"):
            with self.subTest(amount=amount):
                self.assertFalse(
                    validate_csv(HEADER + f"a,{amount},2024-02-29\n")["ok"]
                )
        self.assertTrue(
            validate_csv(HEADER + "a,0.123456789012345678901,2024-02-29\n")["ok"]
        )
        for value in ("2023-02-29", "2026-13-01", "20260910", ""):
            with self.subTest(date=value):
                self.assertFalse(validate_csv(HEADER + f"a,1,{value}\n")["ok"])

    def test_id_whitespace_and_empty(self):
        for rows in ("a,1,2026-01-01\n a ,2,2026-01-01\n", ",1,2026-01-01\n"):
            self.assertFalse(validate_csv(HEADER + rows)["ok"])

    def test_csv_contract(self):
        for text in (
            "",
            "amount,invoice_id,invoice_date\n",
            HEADER + "a,1\n",
            HEADER + 'a,1,"unterminated',
        ):
            with self.subTest(text=text):
                self.assertFalse(validate_csv(text)["ok"])
        self.assertTrue(
            validate_csv("\ufeff" + HEADER + '"a,b",1,2026-01-01\r\n')["ok"]
        )
        self.assertTrue(validate_csv(HEADER)["ok"])

    def test_report_is_bounded_and_omits_cell_contents(self):
        report = validate_csv(HEADER + "PRIVATE-ID,NaN,2026-02-30\n" * 30)
        self.assertEqual(report["error_count"], 89)
        self.assertEqual(len(report["errors"]), 20)
        self.assertTrue(report["errors_truncated"])
        self.assertNotIn("PRIVATE-ID", str(report))
        self.assertNotIn("records", report)
        self.assertFalse(validate_csv("x" * (MAX_CHARS + 1))["ok"])


class CLIIntegrationTests(unittest.TestCase):
    def test_oversized_file_does_not_read_its_invalid_utf8_tail(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "large.csv"
            path.write_bytes(b"x" * (MAX_CHARS * 2) + b"\xff")
            result = subprocess.run(
                [sys.executable, str(EXAMPLE_DIR / "main.py"), str(path)],
                cwd=directory,
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            )
        self.assertEqual(result.returncode, 1, result.stderr)
        report = json.loads(result.stdout)
        self.assertEqual(report["error_count"], 1)
        self.assertEqual(report["rows_read"], 0)
        self.assertEqual(
            report["errors"][0]["message"], f"input exceeds {MAX_CHARS} characters"
        )


class MCPIntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def test_real_agent_round_trip(self):
        for fixture in ("valid.csv", "invalid.csv"):
            with self.subTest(fixture=fixture):
                data = (EXAMPLE_DIR / fixture).read_text()
                report = await asyncio.wait_for(check_csv(data), timeout=30)
                self.assertEqual(report, validate_csv(data))

    async def test_discovery_and_invalid_tool_arguments(self):
        async with (
            make_app().run() as app,
            Agent(name="test", server_names=["csv"], context=app.context) as agent,
        ):
            listed = await agent.list_tools()
            self.assertTrue(any(t.name.endswith("validate_csv") for t in listed.tools))
            result = await agent.call_tool("validate_csv", {"csv_text": 123})
            self.assertTrue(result.isError)


if __name__ == "__main__":
    unittest.main()
