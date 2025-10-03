"""
Invoke an agent or workflow programmatically.
"""

from __future__ import annotations

import asyncio
import json
from typing import Optional
from pathlib import Path

import typer
from rich.console import Console

from mcp_agent.cli.core.utils import (
    load_user_app,
    detect_default_script,
    select_servers_from_config,
)
from mcp_agent.workflows.factory import create_llm


app = typer.Typer(help="Invoke an agent or workflow programmatically")
console = Console(color_system=None)


@app.callback(invoke_without_command=True)
def invoke(
    agent: Optional[str] = typer.Option(None, "--agent"),
    workflow: Optional[str] = typer.Option(None, "--workflow"),
    message: Optional[str] = typer.Option(None, "--message", "-m"),
    vars: Optional[str] = typer.Option(None, "--vars", help="JSON structured inputs"),
    script: Optional[str] = typer.Option(None, "--script"),
    model: Optional[str] = typer.Option(None, "--model"),
    servers: Optional[str] = typer.Option(
        None, "--servers", help="Comma-separated list of MCP server names"
    ),
) -> None:
    """Run either an agent (LLM) or a workflow from the user's app script."""
    if not agent and not workflow:
        typer.secho("Specify --agent or --workflow", err=True, fg=typer.colors.RED)
        raise typer.Exit(6)
    if agent and workflow:
        typer.secho(
            "Specify only one of --agent or --workflow", err=True, fg=typer.colors.RED
        )
        raise typer.Exit(6)

    try:
        payload = json.loads(vars) if vars else {}
    except Exception as e:
        typer.secho(f"Invalid --vars JSON: {e}", err=True, fg=typer.colors.RED)
        raise typer.Exit(6)

    async def _run():
        script_path = detect_default_script(Path(script) if script else None)
        app_obj = load_user_app(script_path)
        await app_obj.initialize()
        async with app_obj.run():
            if agent:
                # Run via LLM
                server_list = select_servers_from_config(servers, None, None)
                llm = create_llm(
                    agent_name=agent,
                    server_names=server_list,
                    provider=None,
                    model=model,
                    context=app_obj.context,
                )
                if message:
                    res = await llm.generate_str(message)
                    console.print(res, end="\n\n\n")
                    return
                if payload:
                    # If structured vars contain messages, prefer that key; else stringify
                    msg = (
                        payload.get("message")
                        or payload.get("input")
                        or json.dumps(payload)
                    )
                    res = await llm.generate_str(msg)
                    console.print(res, end="\n\n\n")
                    return
                typer.secho("No input provided", err=True, fg=typer.colors.YELLOW)
                return

            # Workflow path
            wname = workflow
            wf_cls = app_obj.workflows.get(wname) if wname else None
            if not wf_cls:
                raise RuntimeError(f"Workflow '{wname}' not found in app")

            # Create instance with context
            wf = await wf_cls.create(name=wname, context=app_obj.context)
            # Try running with provided vars
            try:
                if message and "input" not in payload and "message" not in payload:
                    payload["input"] = message
                result = await wf.run(**payload)
            except TypeError:
                # Retry with 'message' key if 'input' didn't fit
                if "message" not in payload and message:
                    result = await wf.run(message=message)
                else:
                    raise
            # If result is a WorkflowResult object, unwrap if possible
            try:
                val = getattr(result, "value", result)
            except Exception:
                val = result
            console.print(val, end="\n\n\n")

    try:
        asyncio.run(_run())
    except KeyboardInterrupt:
        pass
