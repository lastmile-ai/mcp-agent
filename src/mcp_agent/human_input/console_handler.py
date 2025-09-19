import asyncio
from typing import Optional

from rich.panel import Panel
from mcp_agent.console import console
from mcp_agent.human_input.types import HumanInputRequest, HumanInputResponse
from mcp_agent.logging.progress_display import progress_display
from mcp_agent.logging.logger import get_logger

logger = get_logger(__name__)

# Slash command constants
SLASH_COMMANDS = {
    "/decline": "Decline the human input request.",
    "/cancel": "Cancel the human input request.",
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


def _create_panel(request: HumanInputRequest) -> Panel:
    """Generate styled panel for prompts."""
    content = (
        request.description
        and f"[bold]{request.description}[/bold]\n\n{request.prompt}"
        or request.prompt
    )
    content += "\n\n[dim]Type / to see available commands[/dim]"
    return Panel(
        content,
        title="HUMAN INPUT NEEDED",
        style="blue",
        border_style="bold white",
        padding=(1, 2),
    )


async def console_input_callback(request: HumanInputRequest) -> HumanInputResponse:
    """Entry point: handle both simple and schema-based input."""
    # Use context manager if progress_display exists, otherwise just run the code
    if progress_display and hasattr(progress_display, "paused"):
        with progress_display.paused():
            console.print(_create_panel(request))
            response = await _handle_simple_input(request)
    else:
        console.print(_create_panel(request))
        response = await _handle_simple_input(request)
    return HumanInputResponse(request_id=request.request_id, response=response)


async def _handle_simple_input(request: HumanInputRequest) -> str:
    """Handle free-text input."""
    while True:
        if request.timeout_seconds:
            try:
                user_input = await asyncio.wait_for(
                    asyncio.get_event_loop().run_in_executor(
                        None, lambda: console.input("> ")
                    ),
                    request.timeout_seconds,
                )
            except asyncio.TimeoutError:
                console.print("\n[red]Timeout waiting for input[/red]")
                raise TimeoutError(
                    "No response received within timeout period"
                ) from None
        else:
            user_input = await asyncio.get_event_loop().run_in_executor(
                None, lambda: console.input("> ")
            )

        user_input = user_input.strip()
        cmd_result = _process_slash_command(user_input)
        if not cmd_result:
            return user_input
        if cmd_result.action in ("decline", "cancel"):
            return cmd_result.action
        if cmd_result.action == "help":
            _print_slash_help()
            continue
