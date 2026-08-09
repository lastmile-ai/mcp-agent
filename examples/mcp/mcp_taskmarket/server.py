"""
TaskMarket MCP Server

An MCP server that exposes TaskMarket (taskmarket.dev) as tools for AI agents.
- Read tools (browse/get/submissions) use the public REST API (no wallet needed).
- Write tools (claim/subitch/submit/proof) are approval-gated and delegated to
  the first-party `taskmarket` CLI, which owns the wallet, signatures, and X402.

Safety:
- Write tools will NOT auto-sign. Each requires an explicit `approve` boolean.
- No private keys, seed phrases, or tokens are ever accepted or stored as args.
- All wallet identity is handled by the CLI binary itself.
"""

import asyncio
import json
import os
import shutil
import subprocess
from typing import Any, Dict, List, Optional, Union

from mcp import Tool
from mcp.server import Server, InitializationOptions, NotificationOptions
from mcp.server.sse import SseServerTransport
from mcp.types import TextContent, ImageContent, EmbeddedResource, Tool
from pydantic import BaseModel, Field, create_model
from starlette.applications import Starlette
from starlette.routing import Route, Mount


API = os.environ.get("TASKMARKET_API_URL", "https://api.taskmarket.dev")
CLI_BIN = os.environ.get("TASKMARKET_CLI", "taskmarket")


def _bin_path() -> str:
    """Return the resolved CLI binary path, ensuring it exists."""
    path = shutil.which(CLI_BIN)
    if path is None:
        # Common npm-global location used in non-interactive shells
        candidate = os.path.expanduser("~/.npm-global/bin/taskmarket")
        if os.path.isfile(candidate):
            return candidate
    return CLI_BIN


def _run_cli(args: List[str]) -> str:
    """Run a taskmarket CLI command and return stdout as text."""
    bin_path = _bin_path()
    cmd = [bin_path, *args]
    result = subprocess.run(
        cmd, capture_output=True, text=True, timeout=30
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"CLI error ({' '.join(args)}): {result.stderr.strip() or result.stdout.strip()}"
        )
    return result.stdout


def _run_cli_json(args: List[str]) -> Any:
    """Run a taskmarket CLI command and return parsed JSON."""
    raw = _run_cli(args)
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {"raw": raw}


# ---------------------------------------------------------------------------
# Pydantic schemas for tool inputs
# ---------------------------------------------------------------------------

class EmptyInputSchema(BaseModel):
    pass


class GetTaskSchema(BaseModel):
    task_id: str = Field(..., description="The 0x-prefixed task ID.")


class SubmitWorkSchema(BaseModel):
    task_id: str = Field(..., description="The 0x-prefixed task ID to submit work for.")
    content: str = Field(..., description="The deliverable text/content to submit.")
    approve: bool = Field(
        False,
        description="MUST be true to proceed -- write tool requires explicit operator approval.",
    )


class ClaimTaskSchema(BaseModel):
    task_id: str = Field(..., description="The 0x-prefixed task ID to claim.")
    approve: bool = Field(
        False,
        description="MUST be true to proceed -- claim requires explicit operator approval.",
    )


class ProofSchema(BaseModel):
    task_id: str = Field(..., description="The 0x-prefixed benchmark task ID.")
    description: str = Field(..., description="Short description of the proof / verification.")
    approve: bool = Field(
        False,
        description="MUST be true to proceed -- proof submission requires explicit operator approval.",
    )


class CreateTaskSchema(BaseModel):
    title: str = Field(..., description="Task title.")
    description: str = Field(..., description="Full task description (markdown).")
    reward_usdc: float = Field(..., description="Reward in USDC (e.g. 0.50).")
    mode: str = Field("bounty", description="Task mode: bounty, claim, pitch, benchmark, auction.")
    approve: bool = Field(
        False,
        description="MUST be true to proceed -- task creation spends escrow and requires explicit approval.",
    )


class ListTasksSchema(BaseModel):
    limit: int = Field(10, ge=1, le=50, description="Maximum number of tasks to return.")
    tags: Optional[str] = Field(None, description="Comma-separated tags to filter by.")


# ---------------------------------------------------------------------------
# MCP Server setup
# ---------------------------------------------------------------------------

server = Server("taskmarket")


@server.list_tools()
async def handle_list_tools() -> List[Tool]:
    return [
        Tool(
            name="taskmarket_list_open_tasks",
            description=(
                "Browse open TaskMarket tasks. Returns up to N tasks with IDs, rewards, "
                "descriptions, and expiry times. No wallet required."
            ),
            inputSchema=ListTasksSchema.model_json_schema(),
        ),
        Tool(
            name="taskmarket_get_task",
            description=(
                "Fetch full details for a single TaskMarket task by ID. "
                "No wallet required."
            ),
            inputSchema=GetTaskSchema.model_json_schema(),
        ),
        Tool(
            name="taskmarket_list_submissions",
            description=(
                "List all submissions for a task ID. No wallet required."
            ),
            inputSchema=GetTaskSchema.model_json_schema(),
        ),
        Tool(
            name="taskmarket_wallet_address",
            description=(
                "Return the configured wallet address (the CLI owns the wallet)."
            ),
            inputSchema=EmptyInputSchema.model_json_schema(),
        ),
        Tool(
            name="taskmarket_wallet_balance",
            description=(
                "Return USDC balance of the configured wallet."
            ),
            inputSchema=EmptyInputSchema.model_json_schema(),
        ),
        Tool(
            name="taskmarket_claim_task",
            description=(
                "Claim an open claim-mode task. REQUIRES explicit `approve=true`. "
                "The CLI signs the EIP-191 claim message."
            ),
            inputSchema=ClaimTaskSchema.model_json_schema(),
        ),
        Tool(
            name="taskmarket_submit_work",
            description=(
                "Submit work (artifact/content) to a task. REQUIRES explicit `approve=true`. "
                "The CLI signs the EIP-191 submit message."
            ),
            inputSchema=SubmitWorkSchema.model_json_schema(),
        ),
        Tool(
            name="taskmarket_proof",
            description=(
                "Submit a benchmark proof. REQUIRES explicit `approve=true`. "
                "Costs 0.001 USDC."
            ),
            inputSchema=ProofSchema.model_json_schema(),
        ),
        Tool(
            name="taskmarket_create_task",
            description=(
                "Create a new TaskMarket task (escrow USDC). REQUIRES explicit `approve=true`. "
                "The CLI handles wallet, X402, and task creation."
            ),
            inputSchema=CreateTaskSchema.model_json_schema(),
        ),
    ]


@server.call_tool()
async def handle_call_tool(
    name: str, arguments: Optional[Dict[str, Any]]
) -> List[Union[TextContent, ImageContent, EmbeddedResource]]:
    args = arguments or {}

    # ------------------------------------------------------------------
    # Read tools (public API)
    # ------------------------------------------------------------------
    if name == "taskmarket_list_open_tasks":
        import urllib.request

        limit = args.get("limit", 10)
        tags = args.get("tags")
        url = f"{API}/api/tasks?limit={limit}"
        if tags:
            url += f"&tags={tags}"
        with urllib.request.urlopen(url, timeout=15) as resp:
            data = json.loads(resp.read().decode())
        tasks = data.get("data", {}).get("tasks", [])
        summary = []
        for t in tasks:
            summary.append(
                {
                    "id": t.get("id"),
                    "title": t.get("description", "")[:120],
                    "reward_usdc": int(t.get("reward", "0")) / 1e6,
                    "mode": t.get("mode"),
                    "status": t.get("status"),
                    "expiry_time": t.get("expiryTime"),
                    "submission_count": t.get("submissionCount", 0),
                    "net_reward_usdc": int(t.get("netReward", "0")) / 1e6,
                }
            )
        return [TextContent(type="text", text=json.dumps({"tasks": summary}, indent=2))]

    if name == "taskmarket_get_task":
        import urllib.request
        task_id = str(args.get("task_id", ""))
        url = f"{API}/api/tasks/{task_id}"
        try:
            with urllib.request.urlopen(url, timeout=15) as resp:
                data = json.loads(resp.read().decode())
            return [TextContent(type="text", text=json.dumps(data, indent=2))]
        except Exception as e:
            return [TextContent(type="text", text=json.dumps({"error": str(e)}, indent=2))]

    if name == "taskmarket_list_submissions":
        import urllib.request
        task_id = str(args.get("task_id", ""))
        url = f"{API}/api/tasks/{task_id}/submissions"
        try:
            with urllib.request.urlopen(url, timeout=15) as resp:
                data = json.loads(resp.read().decode())
            return [TextContent(type="text", text=json.dumps(data, indent=2))]
        except Exception as e:
            return [TextContent(type="text", text=json.dumps({"error": str(e)}, indent=2))]

    if name == "taskmarket_wallet_address":
        out = _run_cli(["address"])
        data = json.loads(out)
        return [TextContent(type="text", text=json.dumps(data, indent=2))]

    if name == "taskmarket_wallet_balance":
        out = _run_cli(["wallet", "balance"])
        data = json.loads(out)
        return [TextContent(type="text", text=json.dumps(data, indent=2))]

    # ------------------------------------------------------------------
    # Write tools (approval-gated, CLI-backed)
    # ------------------------------------------------------------------
    if name == "taskmarket_claim_task":
        task_id: str = str(args["task_id"])
        approve: bool = bool(args.get("approve", False))
        if not approve:
            return [
                TextContent(
                    type="text",
                    text=(
                        "Approval required. Re-call with `approve=true` to claim this task. "
                        "The CLI will sign the EIP-191 claim message using the configured wallet."
                    ),
                )
            ]
        out = _run_cli(["task", "claim", task_id])
        data = json.loads(out)
        return [TextContent(type="text", text=json.dumps(data, indent=2))]

    if name == "taskmarket_submit_work":
        task_id = str(args["task_id"])
        content = str(args["content"])
        approve = bool(args.get("approve", False))
        if not approve:
            return [
                TextContent(
                    type="text",
                    text=(
                        "Approval required. Re-call with `approve=true` to submit this work. "
                        "The CLI will sign the EIP-191 submit message."
                    ),
                )
            ]
        # Write content to a temp file and submit it as a text artifact
        tmp_path = f"/tmp/taskmarket_submit_{task_id[-12:]}.txt"
        with open(tmp_path, "w") as f:
            f.write(content)
        out = _run_cli(["task", "submit", task_id, "--file", tmp_path])
        data = json.loads(out)
        return [TextContent(type="text", text=json.dumps(data, indent=2))]

    if name == "taskmarket_proof":
        task_id = str(args["task_id"])
        description = str(args["description"])
        approve = bool(args.get("approve", False))
        if not approve:
            return [
                TextContent(
                    type="text",
                    text=(
                        "Approval required. Re-call with `approve=true` to submit this proof. "
                        "Costs 0.001 USDC. The CLI handles signing and payment."
                    ),
                )
            ]
        out = _run_cli(["task", "proof", task_id, "--description", description])
        data = json.loads(out)
        return [TextContent(type="text", text=json.dumps(data, indent=2))]

    if name == "taskmarket_create_task":
        approve = bool(args.get("approve", False))
        if not approve:
            return [
                TextContent(
                    type="text",
                    text=(
                        "Approval required. Re-call with `approve=true` to create this task. "
                        "The CLI will escrow USDC from the configured wallet."
                    ),
                )
            ]
        title = str(args["title"])
        description = str(args["description"])
        reward = str(args["reward_usdc"])
        mode = str(args.get("mode", "bounty"))
        out = _run_cli([
            "task", "create",
            "--title", title,
            "--description", description,
            "--reward", reward,
            "--mode", mode,
        ])
        data = json.loads(out)
        return [TextContent(type="text", text=json.dumps(data, indent=2))]

    return [TextContent(type="text", text=json.dumps({"error": f"Unknown tool: {name}"}))]


# ---------------------------------------------------------------------------
# Entrypoint (SSE transport via Starlette)
# ---------------------------------------------------------------------------

def build_app() -> Starlette:
    sse = SseServerTransport("/messages/")
    initialization_options: InitializationOptions = InitializationOptions(
        server_name=server.name,
        server_version="1.0.0",
        capabilities=server.get_capabilities(
            notification_options=NotificationOptions(),
            experimental_capabilities={},
        ),
    )

    async def handle_sse(request):
        async with sse.connect_sse(
            scope=request.scope, receive=request.receive, send=request._send
        ) as streams:
            await server.run(
                read_stream=streams[0],
                write_stream=streams[1],
                initialization_options=initialization_options,
            )

    return Starlette(
        routes=[
            Route("/sse", endpoint=handle_sse),
            Mount("/messages/", app=sse.handle_post_message),
        ]
    )


app = build_app()


def main():
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info")


if __name__ == "__main__":
    main()
