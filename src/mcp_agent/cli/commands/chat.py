"""
Ephemeral REPL and one-shot chat, supports multi-model fan-out.
Maps "go" functionality to "chat" per the spec.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import List, Optional

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
from mcp_agent.agents.agent import Agent
from mcp_agent.config import get_settings


app = typer.Typer(help="Ephemeral REPL for quick iteration")
console = Console()


async def _run_single_model(
    *,
    script: Path,
    servers: Optional[List[str]],
    url_servers,
    stdio_servers,
    model: Optional[str],
    message: Optional[str],
    prompt_file: Optional[Path],
    agent_name: str,
):
    from mcp.types import TextContent
    from mcp_agent.utils.prompt_message_multipart import PromptMessageMultipart

    app_obj = load_user_app(script)
    await app_obj.initialize()
    attach_url_servers(app_obj, url_servers)
    attach_stdio_servers(app_obj, stdio_servers)

    async with app_obj.run():
        provider = None
        model_id = model
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
            provider = model_id.split(":", 1)[0]

        llm = create_llm(
            agent_name=agent_name,
            server_names=servers or [],
            provider=(provider or "openai"),
            model=model_id,
            context=app_obj.context,
        )

        if message:
            return await llm.generate_str(message)
        if prompt_file:
            text = prompt_file.read_text(encoding="utf-8")
            multipart = [
                PromptMessageMultipart(
                    role="user", content=[TextContent(type="text", text=text)]
                )
            ]
            msgs = []
            for mp in multipart:
                msgs.extend(mp.from_multipart())
            return await llm.generate_str(msgs)
        return "(no input)"


@app.callback(invoke_without_command=True, no_args_is_help=False)
def chat(
    name: Optional[str] = typer.Option(None, "--name"),
    model: Optional[str] = typer.Option(None, "--model"),
    models: Optional[str] = typer.Option(None, "--models"),
    message: Optional[str] = typer.Option(None, "--message", "-m"),
    prompt_file: Optional[Path] = typer.Option(None, "--prompt-file", "-p"),
    servers_csv: Optional[str] = typer.Option(None, "--servers"),
    urls: Optional[str] = typer.Option(None, "--url"),
    auth: Optional[str] = typer.Option(None, "--auth"),
    npx: Optional[str] = typer.Option(None, "--npx"),
    uvx: Optional[str] = typer.Option(None, "--uvx"),
    stdio: Optional[str] = typer.Option(None, "--stdio"),
    script: Optional[Path] = typer.Option(None, "--script"),
    list_servers: bool = typer.Option(False, "--list-servers"),
    list_tools: bool = typer.Option(False, "--list-tools"),
    list_resources: bool = typer.Option(False, "--list-resources"),
    server: Optional[str] = typer.Option(
        None, "--server", help="Filter to a single server"
    ),
) -> None:
    # Resolve script with auto-detection
    script = detect_default_script(script)

    server_list = servers_csv.split(",") if servers_csv else None

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

    stdio_servers = None
    stdio_cmds: List[str] = []
    if npx:
        stdio_cmds.append(f"npx {npx}")
    if uvx:
        stdio_cmds.append(f"uvx {uvx}")
    if stdio:
        stdio_cmds.append(stdio)
    if stdio_cmds:
        from .go import _parse_stdio_commands

        stdio_servers = _parse_stdio_commands(stdio_cmds)
        if stdio_servers:
            if not server_list:
                server_list = list(stdio_servers.keys())
            else:
                server_list.extend(list(stdio_servers.keys()))

    # Smart defaults for servers
    resolved_server_list = select_servers_from_config(
        servers_csv, url_servers, stdio_servers
    )

    # Listing mode (no generation)
    if list_servers or list_tools or list_resources:
        try:

            async def _list():
                # Disable progress display for cleaner listing output
                settings = get_settings()
                if settings.logger:
                    settings.logger.progress_display = False
                app_obj = load_user_app(script, settings_override=settings)
                await app_obj.initialize()
                attach_url_servers(app_obj, url_servers)
                attach_stdio_servers(app_obj, stdio_servers)
                async with app_obj.run():
                    cfg = app_obj.context.config
                    all_servers = (
                        list((cfg.mcp.servers or {}).keys()) if cfg.mcp else []
                    )
                    target_servers = [server] if server else all_servers
                    if list_servers:
                        for s in target_servers:
                            console.print(s)
                        if not (list_tools or list_resources):
                            return
                    agent = Agent(
                        name="chat-lister",
                        instruction="You list tools and resources",
                        server_names=resolved_server_list or target_servers,
                        context=app_obj.context,
                    )
                    async with agent:
                        if list_tools:
                            res = (
                                await agent.list_tools(server_name=server)
                                if server
                                else await agent.list_tools()
                            )
                            for t in res.tools:
                                console.print(t.name)
                        if list_resources:
                            res = (
                                await agent.list_resources(server_name=server)
                                if server
                                else await agent.list_resources()
                            )
                            for r in getattr(res, "resources", []):
                                try:
                                    console.print(r.uri)
                                except Exception:
                                    console.print(str(getattr(r, "uri", "")))

            asyncio.run(_list())
        except KeyboardInterrupt:
            pass
        return

    # Multi-model fan-out
    if models:
        model_list = [x.strip() for x in models.split(",") if x.strip()]
        # Interactive multi-model REPL when no one-shot input
        if (
            not message
            and not prompt_file
            and not (list_servers or list_tools or list_resources)
        ):

            async def _parallel_repl():
                # Disable progress display for cleaner multi-model REPL
                settings = get_settings()
                if settings.logger:
                    settings.logger.progress_display = False
                app_obj = load_user_app(script, settings_override=settings)
                await app_obj.initialize()
                attach_url_servers(app_obj, url_servers)
                attach_stdio_servers(app_obj, stdio_servers)
                async with app_obj.run():
                    # Build one LLM per model
                    llms = []
                    for m in model_list:
                        provider = None
                        if ":" in m:
                            provider = m.split(":", 1)[0]
                        elif "." in m:
                            prov_guess = m.split(".", 1)[0].lower()
                            if prov_guess in {
                                "openai",
                                "anthropic",
                                "azure",
                                "google",
                                "bedrock",
                                "ollama",
                            }:
                                provider = prov_guess
                        llm = create_llm(
                            agent_name=m,
                            server_names=resolved_server_list or [],
                            provider=(provider or "openai"),
                            model=m,
                            context=app_obj.context,
                        )
                        llms.append(llm)

                    console.print(
                        "Interactive parallel chat. Commands: /help, /servers, /tools [server], /resources [server], /models, /clear, /usage, /quit, /exit"
                    )
                    from mcp_agent.agents.agent import Agent as _Agent

                    while True:
                        try:
                            inp = input("> ")
                        except (EOFError, KeyboardInterrupt):
                            break
                        if not inp:
                            continue
                        if inp.startswith("/quit") or inp.startswith("/exit"):
                            break
                        if inp.startswith("/help"):
                            console.print(
                                "/servers, /tools [server], /resources [server], /models, /clear, /usage, /quit, /exit"
                            )
                            continue
                        if inp.startswith("/clear"):
                            console.clear()
                            continue
                        if inp.startswith("/models"):
                            # Show available models
                            console.print(f"\nActive models ({len(llms)}):")
                            for llm in llms:
                                console.print(f"  - {llm.name}")
                            continue
                        if inp.startswith("/servers"):
                            cfg = app_obj.context.config
                            svrs = (
                                list((cfg.mcp.servers or {}).keys()) if cfg.mcp else []
                            )
                            for s in svrs:
                                console.print(s)
                            continue
                        if inp.startswith("/tools"):
                            parts = inp.split()
                            srv = parts[1] if len(parts) > 1 else None
                            ag = _Agent(
                                name="chat-lister",
                                instruction="list tools",
                                server_names=[srv]
                                if srv
                                else (resolved_server_list or []),
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
                                name="chat-lister",
                                instruction="list resources",
                                server_names=[srv]
                                if srv
                                else (resolved_server_list or []),
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
                                from mcp_agent.cli.utils.display import (
                                    TokenUsageDisplay,
                                )

                                # Try to get summary from token counter
                                tc = getattr(app_obj.context, "token_counter", None)
                                if tc:
                                    summary = await tc.get_summary()
                                    if summary:
                                        display = TokenUsageDisplay()
                                        summary_dict = (
                                            summary.model_dump()
                                            if hasattr(summary, "model_dump")
                                            else summary
                                        )
                                        display.show_summary(summary_dict)
                                    else:
                                        console.print("(no usage data)")
                                else:
                                    console.print("(no token counter)")
                            except Exception as e:
                                console.print(f"(usage error: {e})")
                            continue

                        # Broadcast input to all models and print results
                        try:
                            from mcp_agent.cli.utils.display import (
                                ParallelResultsDisplay,
                            )

                            async def _gen(llm_instance):
                                try:
                                    return (
                                        llm_instance.name,
                                        await llm_instance.generate_str(inp),
                                    )
                                except Exception as e:
                                    return llm_instance.name, f"ERROR: {e}"

                            results = await asyncio.gather(
                                *[_gen(item) for item in llms]
                            )
                            display = ParallelResultsDisplay()
                            display.show_results(results)
                        except Exception as e:
                            console.print(f"ERROR: {e}")

            asyncio.run(_parallel_repl())
            return

        # One-shot multi-model
        results = []
        for m in model_list:
            try:
                out = asyncio.run(
                    _run_single_model(
                        script=script,
                        servers=resolved_server_list,
                        url_servers=url_servers,
                        stdio_servers=stdio_servers,
                        model=m,
                        message=message,
                        prompt_file=prompt_file,
                        agent_name=name or m,
                    )
                )
                results.append((m, out))
            except Exception as e:
                results.append((m, f"ERROR: {e}"))
        for m, out in results:
            console.print(f"\n[bold]{m}[/bold]:\n{out}")
        return

    # Single model path
    try:
        if (
            not message
            and not prompt_file
            and not models
            and not (list_servers or list_tools or list_resources)
        ):
            # Interactive loop - disable progress display for cleaner REPL experience
            async def _repl():
                settings = get_settings()
                if settings.logger:
                    settings.logger.progress_display = False
                app_obj = load_user_app(script, settings_override=settings)
                await app_obj.initialize()
                attach_url_servers(app_obj, url_servers)
                attach_stdio_servers(app_obj, stdio_servers)
                async with app_obj.run():
                    provider = None
                    model_id = model
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
                        provider = model_id.split(":", 1)[0]
                    llm = create_llm(
                        agent_name=(name or "chat"),
                        server_names=resolved_server_list or [],
                        provider=(provider or "openai"),
                        model=model_id,
                        context=app_obj.context,
                    )
                    console.print(
                        "Interactive chat. Commands: /help, /servers, /tools [server], /resources [server], /models, /prompt <name> [args-json], /apply <file>, /attach <server> <resource-uri>, /history [clear], /save <file>, /clear, /usage, /quit, /exit, /model <name>"
                    )
                    last_output: str | None = None
                    attachments: list[str] = []
                    while True:
                        try:
                            inp = input("> ")
                        except (EOFError, KeyboardInterrupt):
                            break
                        if not inp:
                            continue
                        if inp.startswith("/quit") or inp.startswith("/exit"):
                            break
                        if inp.startswith("/help"):
                            console.print(
                                "/servers, /tools [server], /resources [server], /models, /prompt <name> [args-json], /apply <file>, /attach <server> <resource-uri>, /history [clear], /save <file>, /clear, /usage, /quit, /exit"
                            )
                            continue
                        if inp.startswith("/clear"):
                            console.clear()
                            continue
                        if inp.startswith("/models"):
                            # Show available models
                            from mcp_agent.workflows.llm.llm_selector import (
                                load_default_models,
                            )

                            models = load_default_models()
                            console.print("\n[bold]Available models:[/bold]")
                            current_model_str = str(model_id) if model_id else "default"
                            console.print(f"Current: {current_model_str}\n")
                            for m in models[:15]:  # Show first 15
                                console.print(f"  {m.provider}.{m.name}")
                            if len(models) > 15:
                                console.print(f"  ... and {len(models) - 15} more")
                            continue
                        if inp.startswith("/model "):
                            # Switch current model on the fly
                            try:
                                new_model = inp.split(" ", 1)[1].strip()
                                if not new_model:
                                    console.print(
                                        "Usage: /model <provider.model or provider:model>"
                                    )
                                    continue
                                model_id = new_model
                                prov = None
                                if ":" in new_model:
                                    prov = new_model.split(":", 1)[0]
                                elif "." in new_model:
                                    prov = new_model.split(".", 1)[0]
                                # Recreate LLM with new model
                                llm_local = create_llm(
                                    agent_name=(name or "chat"),
                                    server_names=resolved_server_list or [],
                                    provider=(prov or "openai"),
                                    model=model_id,
                                    context=app_obj.context,
                                )
                                llm = llm_local
                                console.print(f"Switched model to: {model_id}")
                            except Exception as e:
                                console.print(f"/model error: {e}")
                            continue
                        if inp.startswith("/servers"):
                            cfg = app_obj.context.config
                            servers = (
                                list((cfg.mcp.servers or {}).keys()) if cfg.mcp else []
                            )
                            for s in servers:
                                console.print(s)
                            continue
                        if inp.startswith("/tools"):
                            from mcp_agent.cli.utils.display import format_tool_list

                            parts = inp.split()
                            srv = parts[1] if len(parts) > 1 else None
                            ag = Agent(
                                name="chat-lister",
                                instruction="list tools",
                                server_names=[srv]
                                if srv
                                else (resolved_server_list or []),
                                context=app_obj.context,
                            )
                            async with ag:
                                res = (
                                    await ag.list_tools(server_name=srv)
                                    if srv
                                    else await ag.list_tools()
                                )
                                format_tool_list(res.tools, server_name=srv)
                            continue
                        if inp.startswith("/resources"):
                            from mcp_agent.cli.utils.display import format_resource_list

                            parts = inp.split()
                            srv = parts[1] if len(parts) > 1 else None
                            ag = Agent(
                                name="chat-lister",
                                instruction="list resources",
                                server_names=[srv]
                                if srv
                                else (resolved_server_list or []),
                                context=app_obj.context,
                            )
                            async with ag:
                                res = (
                                    await ag.list_resources(server_name=srv)
                                    if srv
                                    else await ag.list_resources()
                                )
                                format_resource_list(
                                    getattr(res, "resources", []), server_name=srv
                                )
                            continue
                        if inp.startswith("/prompt"):
                            try:
                                # Usage: /prompt <name> [args-json]
                                parts = inp.split(maxsplit=2)
                                if len(parts) < 2:
                                    console.print("Usage: /prompt <name> [args-json]")
                                    continue
                                prompt_name = parts[1]
                                args_json = parts[2] if len(parts) > 2 else None
                                arguments = None
                                if args_json:
                                    import json as _json

                                    try:
                                        arguments = _json.loads(args_json)
                                    except Exception as e:
                                        console.print(f"Invalid JSON: {e}")
                                        continue

                                # Use Agent.create_prompt for flexibility
                                ag = llm.agent
                                prompt_msgs = await ag.create_prompt(
                                    prompt_name=prompt_name,
                                    arguments=arguments,
                                    server_names=resolved_server_list or [],
                                )
                                # Generate with prompt messages
                                out = await llm.generate_str(prompt_msgs)
                                last_output = out
                                console.print(out)
                            except Exception as e:
                                console.print(f"/prompt error: {e}")
                            continue
                        if inp.startswith("/apply"):
                            # Load messages or text from file and send
                            parts = inp.split(maxsplit=1)
                            if len(parts) < 2:
                                console.print("Usage: /apply <file>")
                                continue
                            from pathlib import Path as _Path

                            p = _Path(parts[1]).expanduser()
                            if not p.exists():
                                console.print("File not found")
                                continue
                            text = p.read_text(encoding="utf-8")
                            # Try JSON for structured messages, else treat as text
                            try:
                                import json as _json

                                js = _json.loads(text)
                                out = await llm.generate_str(js)
                            except Exception:
                                out = await llm.generate_str(text)
                            last_output = out
                            console.print(out)
                            continue
                        if inp.startswith("/attach"):
                            # Attach a resource: /attach <server> <uri>
                            parts = inp.split(maxsplit=2)
                            if len(parts) < 3:
                                console.print("Usage: /attach <server> <resource-uri>")
                                continue
                            srv, uri = parts[1], parts[2]
                            try:
                                res = await llm.read_resource(uri=uri, server_name=srv)
                                # Try to extract text
                                content_text = None
                                try:
                                    from mcp_agent.utils.content_utils import (
                                        get_text,
                                    )

                                    if getattr(res, "contents", None):
                                        for c in res.contents:
                                            try:
                                                content_text = get_text(c)
                                                if content_text:
                                                    break
                                            except Exception:
                                                continue
                                except Exception:
                                    pass
                                if not content_text:
                                    content_text = str(res)
                                attachments.append(content_text)
                                console.print(
                                    f"Attached resource; size={len(content_text)} chars"
                                )
                            except Exception as e:
                                console.print(f"/attach error: {e}")
                            continue
                        if inp.startswith("/history"):
                            parts = inp.split()
                            if len(parts) > 1 and parts[1] == "clear":
                                try:
                                    llm.history.clear()
                                    console.print("History cleared")
                                except Exception:
                                    console.print("Could not clear history")
                            else:
                                try:
                                    hist = llm.history.get()
                                    console.print(f"{len(hist)} messages in memory")
                                except Exception:
                                    console.print("(no history)")
                            continue
                        if inp.startswith("/save"):
                            parts = inp.split(maxsplit=1)
                            if len(parts) < 2:
                                console.print("Usage: /save <file>")
                                continue
                            if last_output is None:
                                console.print("No output to save")
                                continue
                            from pathlib import Path as _Path

                            _Path(parts[1]).expanduser().write_text(
                                last_output, encoding="utf-8"
                            )
                            console.print("Saved")
                            continue
                        if inp.startswith("/usage"):
                            try:
                                from mcp_agent.cli.utils.display import (
                                    TokenUsageDisplay,
                                )

                                tc = getattr(app_obj.context, "token_counter", None)
                                if tc:
                                    summary = await tc.get_summary()
                                    if summary:
                                        display = TokenUsageDisplay()
                                        summary_dict = (
                                            summary.model_dump()
                                            if hasattr(summary, "model_dump")
                                            else summary
                                        )
                                        display.show_summary(summary_dict)
                                    else:
                                        console.print("(no usage data)")
                                else:
                                    console.print("(no token counter)")
                            except Exception as e:
                                console.print(f"(usage error: {e})")
                            continue
                        # Regular message
                        try:
                            # Prepend any attachments once and then clear
                            payload = inp
                            if attachments:
                                prefix = "\n\n".join(attachments) + "\n\n"
                                payload = prefix + inp
                                attachments.clear()
                            out = await llm.generate_str(payload)
                            last_output = out
                            console.print(out)
                        except Exception as e:
                            console.print(f"ERROR: {e}")

            asyncio.run(_repl())
        else:
            out = asyncio.run(
                _run_single_model(
                    script=script,
                    servers=resolved_server_list,
                    url_servers=url_servers,
                    stdio_servers=stdio_servers,
                    model=model,
                    message=message,
                    prompt_file=prompt_file,
                    agent_name=name or "chat",
                )
            )
            console.print(out)
    except KeyboardInterrupt:
        pass
