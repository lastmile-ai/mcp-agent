"""Call the CSV tool through an Agent, without attaching an LLM."""

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Any

from mcp.types import TextContent

from mcp_agent.agents.agent import Agent
from mcp_agent.app import MCPApp
from mcp_agent.config import (
    LoggerSettings,
    MCPServerSettings,
    MCPSettings,
    OpenTelemetrySettings,
    Settings,
    UsageTelemetrySettings,
)

EXAMPLE_DIR = Path(__file__).resolve().parent


def make_app() -> MCPApp:
    return MCPApp(
        name="csv_preflight",
        settings=Settings(
            execution_engine="asyncio",
            mcp=MCPSettings(
                servers={
                    "csv": MCPServerSettings(
                        command=sys.executable,
                        args=[str(EXAMPLE_DIR / "server.py")],
                    )
                }
            ),
            logger=LoggerSettings(type="none", transports=["none"]),
            otel=OpenTelemetrySettings(enabled=False),
            usage_telemetry=UsageTelemetrySettings(enabled=False),
        ),
    )


async def check_csv(csv_text: str) -> dict[str, Any]:
    app = make_app()
    async with (
        app.run(),
        Agent(
            name="invoice_checker",
            instruction="Use validate_csv to check invoice data. Do not import or modify it.",
            server_names=["csv"],
            context=app.context,
        ) as agent,
    ):
        result = await agent.call_tool("validate_csv", {"csv_text": csv_text})
        if result.isError:
            raise RuntimeError(
                "CSV MCP tool failed; no validation decision is available"
            )
        for content in result.content:
            if isinstance(content, TextContent):
                report = json.loads(content.text)
                if isinstance(report, dict) and isinstance(report.get("ok"), bool):
                    return report
        raise RuntimeError("CSV MCP tool returned no validation report")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "csv_file", nargs="?", type=Path, default=EXAMPLE_DIR / "valid.csv"
    )
    args = parser.parse_args()
    try:
        report = asyncio.run(check_csv(args.csv_file.read_text(encoding="utf-8")))
    except Exception as exc:  # noqa: BLE001 -- CLI boundary also handles MCP ExceptionGroups.
        print(f"Unable to validate CSV: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(report, indent=2))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
