"""
Run an interactive agent quickly.
This will load the user's MCPApp from a script (if provided), attach dynamic servers
from URLs or stdio launchers, and run a one-shot message or interactive session.
"""

from __future__ import annotations

import asyncio
import shlex
from pathlib import Path
from typing import Dict, List, Optional

import typer
from rich.console import Console

from mcp_agent.cli.core.utils import (
    attach_stdio_servers,
    attach_url_servers,
    load_user_app,
    detect_default_script,
    select_servers_from_config,
)
from mcp_agent.cli.utils.url_parser import generate_server_configs, parse_server_urls
from mcp_agent.workflows.factory import create_llm


app = typer.Typer(
    help="Run an interactive agent quickly",
    context_settings={"allow_extra_args": True, "ignore_unknown_options": True},
)
console = Console()


def _resolve_instruction_arg(instruction: Optional[str]) -> Optional[str]:
    if not instruction:
        return None
    try:
        if instruction.startswith("text:"):
            return instruction[len("text:") :]
        if instruction.startswith("http://") or instruction.startswith("https://"):
            try:
                import httpx  # type: ignore

                r = httpx.get(instruction, timeout=10.0)
                r.raise_for_status()
                return r.text
            except Exception:
                # Fallback to urllib
                try:
                    from urllib.request import urlopen

                    with urlopen(instruction, timeout=10) as resp:  # type: ignore
                        return resp.read().decode("utf-8")
                except Exception as e:
                    raise typer.Exit(6) from e
        p = Path(instruction).expanduser()
        if p.exists() and p.is_file():
            return p.read_text(encoding="utf-8")
        # Otherwise treat as raw text
        return instruction
    except Exception:
        return instruction


async def _run_agent(
    *,
    app_script: Optional[Path],
    server_list: Optional[List[str]],
    model: Optional[str],
    message: Optional[str],
    prompt_file: Optional[Path],
    url_servers: Optional[Dict[str, Dict[str, str]]],
    stdio_servers: Optional[Dict[str, Dict[str, str]]],
    agent_name: Optional[str],
    instruction: Optional[str],
):
    # Placeholder: future structured prompt parsing will use PromptMessageMultipart

    app_obj = load_user_app(app_script) if app_script else None
    if app_obj is None:
        raise typer.Exit(2)

    # Initialize app to have context
    await app_obj.initialize()

    # Attach dynamic servers
    attach_url_servers(app_obj, url_servers)
    attach_stdio_servers(app_obj, stdio_servers)

    async with app_obj.run():
        # Prepare LLM in the app context
        provider = None
        model_id = model
        # Heuristic: allow provider prefix like "anthropic.model" or "openai:model"
        if model_id and ":" not in model_id and "." in model_id:
            maybe_provider = model_id.split(".", 1)[0].lower()
            if maybe_provider in {
                "openai",
                "anthropic",
                "azure",
                "google",
                "bedrock",
                "ollama",
            }:
                provider = maybe_provider
        if model_id and ":" in model_id:
            # provider:model pattern
            provider = model_id.split(":", 1)[0]

        llm = create_llm(
            agent_name=agent_name or "cli-agent",
            server_names=server_list or [],
            provider=(provider or "openai"),
            model=model_id,
            instruction=_resolve_instruction_arg(instruction) if instruction else None,
            context=app_obj.context,
        )

        if message:
            try:
                result = await llm.generate_str(message)
                console.print(result)
            except Exception as e:
                typer.secho(f"Generation failed: {e}", err=True, fg=typer.colors.RED)
                raise typer.Exit(5)
        elif prompt_file:
            try:
                from mcp.types import TextContent
                from mcp_agent.utils.prompt_message_multipart import (
                    PromptMessageMultipart,
                )

                text = prompt_file.read_text(encoding="utf-8")
                # Convert to a single multipart user message for downstream LLM/workflow
                multipart_messages = [
                    PromptMessageMultipart(
                        role="user", content=[TextContent(type="text", text=text)]
                    )
                ]
                # Flatten to standard PromptMessage sequence
                prompt_messages = []
                for mp in multipart_messages:
                    prompt_messages.extend(mp.from_multipart())
                result = await llm.generate_str(prompt_messages)
                console.print(result)
            except Exception as e:
                typer.secho(
                    f"Failed to read prompt file: {e}", err=True, fg=typer.colors.RED
                )
                raise typer.Exit(6)
        else:
            # Interactive REPL similar to chat
            console.print(
                "Interactive chat. Commands: /help, /servers, /tools [server], /resources [server], /usage, /quit"
            )
            from mcp_agent.agents.agent import Agent as _Agent

            while True:
                try:
                    inp = input("> ")
                except (EOFError, KeyboardInterrupt):
                    break
                if not inp:
                    continue
                if inp.startswith("/quit"):
                    break
                if inp.startswith("/help"):
                    console.print(
                        "/servers, /tools [server], /resources [server], /usage, /quit"
                    )
                    continue
                if inp.startswith("/servers"):
                    cfg = app_obj.context.config
                    svrs = list((cfg.mcp.servers or {}).keys()) if cfg.mcp else []
                    for s in svrs:
                        console.print(s)
                    continue
                if inp.startswith("/tools"):
                    parts = inp.split()
                    srv = parts[1] if len(parts) > 1 else None
                    ag = _Agent(
                        name="go-lister",
                        instruction="list tools",
                        server_names=[srv] if srv else (server_list or []),
                        context=app_obj.context,
                    )
                    async with ag:
                        res = (
                            await ag.list_tools(server_name=srv)
                            if srv
                            else await ag.list_tools()
                        )
                        for t in res.tools:
                            console.print(t.name)
                    continue
                if inp.startswith("/resources"):
                    parts = inp.split()
                    srv = parts[1] if len(parts) > 1 else None
                    ag = _Agent(
                        name="go-lister",
                        instruction="list resources",
                        server_names=[srv] if srv else (server_list or []),
                        context=app_obj.context,
                    )
                    async with ag:
                        res = (
                            await ag.list_resources(server_name=srv)
                            if srv
                            else await ag.list_resources()
                        )
                        for r in getattr(res, "resources", []):
                            try:
                                console.print(r.uri)
                            except Exception:
                                console.print(str(getattr(r, "uri", "")))
                    continue
                if inp.startswith("/usage"):
                    try:
                        tc = getattr(app_obj.context, "token_counter", None)
                        if tc:
                            summary = await tc.get_summary()
                            console.print(
                                summary.model_dump()
                                if hasattr(summary, "model_dump")
                                else summary
                            )
                    except Exception:
                        console.print("(no usage)")
                    continue
                # Regular prompt
                try:
                    result = await llm.generate_str(inp)
                    console.print(result)
                except Exception as e:
                    typer.secho(
                        f"Generation failed: {e}", err=True, fg=typer.colors.RED
                    )
                    continue


def _parse_stdio_commands(cmds: List[str] | None) -> Dict[str, Dict[str, str]] | None:
    if not cmds:
        return None
    servers: Dict[str, Dict[str, str]] = {}
    for i, cmd in enumerate(cmds):
        parts = shlex.split(cmd)
        if not parts:
            continue
        command, args = parts[0], parts[1:]
        name = command.replace("/", "_").replace("@", "").replace(".", "_")
        if len(cmds) > 1:
            name = f"{name}_{i + 1}"
        servers[name] = {"transport": "stdio", "command": command, "args": args}
    return servers


@app.callback(invoke_without_command=True, no_args_is_help=False)
def go(
    ctx: typer.Context,
    name: str = typer.Option("mcp-agent", "--name"),
    instruction: Optional[str] = typer.Option(None, "--instruction", "-i"),
    config_path: Optional[str] = typer.Option(None, "--config-path", "-c"),
    servers: Optional[str] = typer.Option(None, "--servers"),
    urls: Optional[str] = typer.Option(None, "--url"),
    auth: Optional[str] = typer.Option(None, "--auth"),
    model: Optional[str] = typer.Option(None, "--model", "--models"),
    message: Optional[str] = typer.Option(None, "--message", "-m"),
    prompt_file: Optional[Path] = typer.Option(None, "--prompt-file", "-p"),
    npx: Optional[str] = typer.Option(None, "--npx"),
    uvx: Optional[str] = typer.Option(None, "--uvx"),
    stdio: Optional[str] = typer.Option(None, "--stdio"),
    script: Optional[Path] = typer.Option(None, "--script"),
) -> None:
    # Resolve script with auto-detection
    script = detect_default_script(script)

    # Parse server names from config if provided
    server_list = servers.split(",") if servers else None

    # Parse URLs
    url_servers = None
    if urls:
        try:
            parsed = parse_server_urls(urls, auth)
            url_servers = generate_server_configs(parsed)
            if url_servers and not server_list:
                server_list = list(url_servers.keys())
            elif url_servers and server_list:
                server_list.extend(list(url_servers.keys()))
        except ValueError as e:
            typer.secho(f"Error parsing URLs: {e}", err=True, fg=typer.colors.RED)
            raise typer.Exit(6)

    # Parse stdio launchers
    stdio_cmds: List[str] = []
    if npx:
        stdio_cmds.append(f"npx {npx}")
    if uvx:
        stdio_cmds.append(f"uvx {uvx}")
    if stdio:
        stdio_cmds.append(stdio)
    stdio_servers = _parse_stdio_commands(stdio_cmds)
    if stdio_servers:
        if not server_list:
            server_list = list(stdio_servers.keys())
        else:
            server_list.extend(list(stdio_servers.keys()))

    # Smart defaults from config if still unspecified
    resolved_server_list = select_servers_from_config(
        ",".join(server_list) if server_list else None, url_servers, stdio_servers
    )

    # Multi-model support if comma-separated
    if model and "," in model:
        models = [m.strip() for m in model.split(",") if m.strip()]
        results: list[tuple[str, str | Exception]] = []
        for m in models:
            try:
                asyncio.run(
                    _run_agent(
                        app_script=script,
                        server_list=resolved_server_list,
                        model=m,
                        message=message,
                        prompt_file=prompt_file,
                        url_servers=url_servers,
                        stdio_servers=stdio_servers,
                        agent_name=name,
                        instruction=instruction,
                    )
                )
            except Exception as e:
                results.append((m, e))
        # No consolidated pretty-print; leave to chat for advanced
        return

    # Run under asyncio
    try:
        asyncio.run(
            _run_agent(
                app_script=script,
                server_list=resolved_server_list,
                model=model,
                message=message,
                prompt_file=prompt_file,
                url_servers=url_servers,
                stdio_servers=stdio_servers,
                agent_name=name,
                instruction=instruction,
            )
        )
    except KeyboardInterrupt:
        pass
