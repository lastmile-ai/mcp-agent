from typing import Optional


def format_workflow_status(status: Optional[str] = None) -> str:
    """Format the execution status text."""
    if not status:
        return "❓ Unknown"

    status_lower = str(status).lower()

    if "running" in status_lower:
        return "[green]🔄 Running[/green]"
    elif "failed" in status_lower or "error" in status_lower:
        return "[red]❌ Failed[/red]"
    elif "timeout" in status_lower or "timed_out" in status_lower:
        return "[red]⌛ Timed Out[/red]"
    elif "cancel" in status_lower:
        return "[yellow]🚫 Cancelled[/yellow]"
    elif "terminat" in status_lower:
        return "[red]🛑 Terminated[/red]"
    elif "complet" in status_lower:
        return "[green]✅ Completed[/green]"
    elif "continued" in status_lower:
        return "[blue]🔁 Continued as New[/blue]"
    else:
        return f"❓ {status}"
