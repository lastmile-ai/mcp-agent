from datetime import datetime
from typing import Optional
from mcp_agent.cli.mcp_app.mcp_client import WorkflowRun
from mcp_agent.cli.utils.ux import console, print_info


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


def print_workflow_runs(
    runs: list[WorkflowRun], status_filter: Optional[str] = None
) -> None:
    """Print workflows in text format."""
    console.print(f"\n[bold blue] Workflow Runs ({len(runs)})[/bold blue]")

    if not runs:
        print_info("No workflow runs found.")
        return

    for i, workflow in enumerate(runs):
        if i > 0:
            console.print()

        workflow_id = (
            getattr(workflow.temporal, "workflow_id", "Unknown")
            if workflow.temporal
            else "Unknown"
        )
        name = getattr(workflow, "name", "Unknown")
        execution_status = getattr(workflow, "status", "Unknown")
        run_id = getattr(workflow, "id", "Unknown")
        started_at = (
            getattr(workflow.temporal, "start_time", "Unknown")
            if workflow.temporal
            else "Unknown"
        )

        status_display = format_workflow_status(execution_status)

        if started_at and started_at != "Unknown":
            if hasattr(started_at, "strftime"):
                started_display = started_at.strftime("%Y-%m-%d %H:%M:%S")
            else:
                try:
                    if isinstance(started_at, (int, float)):
                        dt = datetime.fromtimestamp(started_at)
                    else:
                        dt = datetime.fromisoformat(
                            str(started_at).replace("Z", "+00:00")
                        )
                    started_display = dt.strftime("%Y-%m-%d %H:%M:%S")
                except (ValueError, TypeError):
                    started_display = str(started_at)
        else:
            started_display = "Unknown"

        console.print(f"[bold cyan]{name or 'Unnamed'}[/bold cyan] {status_display}")
        console.print(f"  Workflow ID: {workflow_id}")
        console.print(f"  Run ID: {run_id}")
        console.print(f"  Started: {started_display}")

    if status_filter:
        console.print(f"\n[dim]Filtered by status: {status_filter}[/dim]")
