import asyncio
from rich.panel import Panel

from mcp_agent.console import console
from mcp_agent.human_input.types import (
    HumanInputRequest,
    HumanInputResponse,
)
from mcp_agent.progress_display import progress_display


async def console_input_callback(request: HumanInputRequest) -> HumanInputResponse:
    """Request input from a human user via console using rich panel and prompt."""

    # Prepare the prompt text
    prompt_text = request.prompt
    if request.description:
        prompt_text = f"[bold]{request.description}[/bold]\n\n{request.prompt}"

    # Create a panel with the prompt
    panel = Panel(
        prompt_text,
        title="HUMAN INPUT NEEDED",
        style="blue",
        border_style="bold white",
        padding=(1, 2),
    )

    # Use the context manager to pause the progress display while getting input
    with progress_display.paused():
        console.print(panel)

        if request.timeout_seconds:
            try:
                loop = asyncio.get_event_loop()
                response = await asyncio.wait_for(
                    loop.run_in_executor(None, lambda: console.input()),
                    request.timeout_seconds,
                )
            except asyncio.TimeoutError:
                console.print("\n[red]Timeout waiting for input[/red]")
                raise TimeoutError("No response received within timeout period")
        else:
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(None, lambda: console.input())

    return HumanInputResponse(request_id=request.request_id, response=response.strip())
