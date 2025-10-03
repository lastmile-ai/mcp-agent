import json
from typing import Any, Optional

from rich.panel import Panel
from mcp_agent.console import console
from mcp_agent.elicitation.types import ElicitRequestParams, ElicitResult
from mcp_agent.logging.progress_display import progress_display
from mcp_agent.logging.logger import get_logger


logger = get_logger(__name__)

SLASH_COMMANDS = {
    "/decline": "Decline the elicitation request.",
    "/cancel": "Cancel the elicitation request.",
    "/help": "Show available commands",
}


class SlashCommandResult:
    def __init__(self, command: str, action: str):
        self.command = command
        self.action = action


def _process_slash_command(input_text: str) -> Optional[SlashCommandResult]:
    """Detect and map slash commands to actions."""
    if not input_text.startswith("/"):
        return None
    cmd = input_text.strip().lower()
    action = {
        "/decline": "decline",
        "/cancel": "cancel",
        "/help": "help",
    }.get(cmd, "unknown" if cmd != "/" else "help")

    if action == "unknown":
        console.print(f"\n[red]Unknown command: {cmd}[/red]")
        console.print("[dim]Type /help for available commands[/dim]\n")
    return SlashCommandResult(cmd, action)


def _print_slash_help() -> None:
    """Display available slash commands."""
    console.print("\n[cyan]Available commands:[/cyan]")
    for cmd, desc in SLASH_COMMANDS.items():
        console.print(f"  [green]{cmd}[/green] - {desc}")
    console.print()


def _process_field_value(field_type: str, value: str) -> Any:
    if field_type == "boolean":
        v = value.lower()
        if v in ("true", "yes", "y", "1"):
            return True
        if v in ("false", "no", "n", "0"):
            return False
        console.print(f"[red]Invalid boolean value: {value}[/red]")
        return None
    if field_type == "number":
        try:
            return float(value)
        except ValueError:
            console.print(f"[red]Invalid number: {value}[/red]")
            return None
    if field_type == "integer":
        try:
            return int(value)
        except ValueError:
            console.print(f"[red]Invalid integer: {value}[/red]")
            return None
    return value


def _create_panel(request: ElicitRequestParams) -> Panel:
    """Generate styled panel for prompts."""
    title = (
        f"ELICITATION RESPONSE NEEDED FROM: {request.server_name}"
        if request.server_name
        else "ELICITATION RESPONSE NEEDED"
    )
    content = f"[bold]Elicitation Request[/bold]\n\n{request.message}"
    content += "\n\n[dim]Type / to see available commands[/dim]"
    return Panel(
        content, title=title, style="blue", border_style="bold white", padding=(1, 2)
    )


async def _handle_elicitation_requested_schema(request: ElicitRequestParams) -> str:
    """Prompt for structured input based on requested schema."""
    schema = request.requestedSchema
    if not schema or "properties" not in schema:
        raise ValueError("Invalid schema: must contain 'properties'")

    result = {}
    for name, props in schema["properties"].items():
        prompt_text = f"Enter {name}"
        if desc := props.get("description"):
            prompt_text += f" - {desc}"
        default = props.get("default")
        loop_prompt = (
            f"{prompt_text}{f' [default: {default}]' if default is not None else ''}"
        )

        while True:
            console.print(f"\n{loop_prompt}", style="cyan", markup=False)
            console.print("[dim]Type / to see available commands[/dim]")
            # Show type-specific input hints
            field_type = props.get("type", "string")
            if field_type == "boolean":
                console.print("[dim]Enter: true/false, yes/no, y/n, or 1/0[/dim]")
            elif field_type == "number":
                console.print("[dim]Enter a decimal number[/dim]")
            elif field_type == "integer":
                console.print("[dim]Enter a whole number[/dim]")

            # Show optional hint when a default exists
            if default is not None:
                console.print(f"[dim]Press Enter to accept default [{default}][/dim]")

            value = console.input("> ").strip() or (
                str(default) if default is not None else ""
            )
            cmd_result = _process_slash_command(value)
            if cmd_result:
                if cmd_result.action in ("decline", "cancel"):
                    return cmd_result.action
                if cmd_result.action == "help":
                    _print_slash_help()
                    continue
            processed = _process_field_value(props.get("type", "string"), value)
            if processed is not None:
                result[name] = processed
                break
    return json.dumps(result)


async def console_elicitation_callback(request: ElicitRequestParams):
    """Handle elicitation request in console."""
    # Use context manager if progress_display exists, otherwise just run the code
    if progress_display and hasattr(progress_display, "paused"):
        with progress_display.paused():
            console.print(_create_panel(request))
            response = await _handle_elicitation_requested_schema(request)
            try:
                content = json.loads(response)
                logger.info("User accepted elicitation", data=content)
                return ElicitResult(action="accept", content=content)
            except json.JSONDecodeError:
                logger.debug(
                    "Error parsing elicitation response. Cancelling elicitation...",
                    data=response,
                )
                return ElicitResult(action="cancel")
    else:
        console.print(_create_panel(request))
        response = await _handle_elicitation_requested_schema(request)
        try:
            content = json.loads(response)
            logger.info("User accepted elicitation", data=content)
            return ElicitResult(action="accept", content=content)
        except json.JSONDecodeError:
            logger.debug(
                "Error parsing elicitation response. Cancelling elicitation...",
                data=response,
            )
            return ElicitResult(action="cancel")
