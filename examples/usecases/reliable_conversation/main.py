"""
Main entry point for Reliable Conversation Manager.
Implements REPL with conversation-as-workflow pattern.
"""

import asyncio
import sys
import os
import time
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent / "src"))

from mcp_agent.app import MCPApp
from workflows.conversation_workflow import ConversationWorkflow
from models.conversation_models import ConversationState
from utils.logging import get_rcm_logger
from utils.readable_output import ReadableFormatter, OutputConfig
from utils.progress_reporter import ProgressReporter, set_progress_reporter
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

console = Console()

# Create app instance
app = MCPApp(name="reliable_conversation_manager")

# No task registration needed - we import functions directly in workflows

# Register the workflow with the app


@app.workflow
class RegisteredConversationWorkflow(ConversationWorkflow):
    """Workflow registered with app"""

    pass


async def run_repl():
    """Run the RCM REPL interface with readable output"""

    async with app.run() as rcm_app:
        logger = get_rcm_logger("main")

        # Set up output configuration
        rcm_config = getattr(rcm_app.context.config, "rcm", None)
        config = OutputConfig(
            verbosity=getattr(rcm_config, "verbosity", "normal")
            if rcm_config
            else "normal",
            show_quality_bars=True,
            use_color=True,
            show_timing_info=getattr(rcm_config, "show_timing", False)
            if rcm_config
            else False,
        )

        # Create readable formatter and progress reporter
        formatter = ReadableFormatter(console, config)
        progress_reporter = ProgressReporter(
            console,
            enabled=getattr(rcm_config, "show_internal_messages", True)
            if rcm_config
            else True,
        )
        set_progress_reporter(progress_reporter)

        # Add current directory to filesystem server
        if hasattr(rcm_app.context.config, "mcp") and rcm_app.context.config.mcp:
            if "filesystem" in rcm_app.context.config.mcp.servers:
                rcm_app.context.config.mcp.servers["filesystem"].args.extend(
                    [os.getcwd()]
                )

        # Display enhanced welcome message
        formatter.show_welcome("Reliable Conversation Manager")
        console.print(
            f"[dim]Execution Engine: {rcm_app.context.config.execution_engine}[/dim]"
        )
        quality_threshold = (
            getattr(rcm_config, "quality_threshold", 0.8) if rcm_config else 0.8
        )
        console.print(
            f"[dim]Quality control: {'enabled' if quality_threshold > 0 else 'disabled'}[/dim]"
        )
        console.print(
            f"[dim]Internal messages: {'visible' if progress_reporter.enabled else 'hidden'}[/dim]"
        )

        # Check API configuration
        has_openai = (
            hasattr(rcm_app.context.config, "openai") and rcm_app.context.config.openai
        )
        has_anthropic = (
            hasattr(rcm_app.context.config, "anthropic")
            and rcm_app.context.config.anthropic
        )

        if not (has_openai or has_anthropic):
            formatter.show_warning(
                "No LLM providers configured. Using fallback responses."
            )
            console.print(
                "[dim]Add API keys to mcp_agent.secrets.yaml for full functionality[/dim]"
            )
        else:
            provider = "OpenAI" if has_openai else "Anthropic"
            formatter.show_success(f"LLM provider configured: {provider}")

        # Create workflow instance
        workflow = RegisteredConversationWorkflow(app)
        conversation_state = None

        logger.info("RCM REPL started")

        while True:
            # Get user input
            try:
                user_input = console.input("\n[bold cyan]You:[/bold cyan] ")
            except (EOFError, KeyboardInterrupt):
                formatter.show_success("Goodbye!")
                break

            # Handle commands
            if user_input.lower() == "/exit":
                formatter.show_success("Goodbye!")
                break
            elif user_input.lower() == "/stats":
                _display_stats_enhanced(conversation_state, formatter)
                continue
            elif user_input.lower() == "/requirements":
                _display_requirements_enhanced(conversation_state, formatter)
                continue
            elif user_input.lower() == "/help":
                _display_help(formatter)
                continue
            elif user_input.lower() == "/config":
                _display_config(rcm_app, formatter)
                continue

            # Reset progress reporter timer for this turn
            progress_reporter.start_time = time.time()

            # Process turn through workflow with readable output
            try:
                result = await workflow.run(
                    {
                        "user_input": user_input,
                        "state": conversation_state.to_dict()
                        if conversation_state
                        else None,
                    }
                )

                # Extract response and state
                response_data = result.value
                conversation_state = ConversationState.from_dict(response_data["state"])

                # Display conversation turn using formatter
                formatter.format_conversation_turn(
                    user_input=user_input,
                    response=response_data["response"],
                    quality_metrics=response_data.get("metrics", {}),
                    turn_number=response_data["turn_number"],
                )

                logger.info(
                    "Turn completed",
                    data={
                        "turn": response_data["turn_number"],
                        "response_length": len(response_data["response"]),
                    },
                )

            except Exception as e:
                formatter.show_error(f"Error processing turn: {str(e)}")
                logger.error(f"Turn processing error: {str(e)}")

        # Display final summary
        if conversation_state and conversation_state.current_turn > 0:
            _display_final_summary_enhanced(conversation_state, formatter)

        logger.info("RCM REPL ended")


def _display_help(formatter: ReadableFormatter):
    """Display help information"""
    help_text = """[bold]Available Commands:[/bold]

[cyan]/help[/cyan] - Show this help message
[cyan]/stats[/cyan] - Show conversation statistics and research metrics
[cyan]/requirements[/cyan] - Show tracked requirements with status
[cyan]/config[/cyan] - Show current configuration settings
[cyan]/exit[/cyan] - Exit the conversation

[bold]Features:[/bold]
• Quality-controlled responses with 7-dimension evaluation
• Requirement tracking across conversation turns
• Context consolidation to prevent lost-in-middle-turns
• Answer bloat detection and prevention
• Real-time internal workflow visibility

[bold]Research Implementation:[/bold]
Based on "LLMs Get Lost in Multi-Turn Conversation" findings"""

    formatter.console.print(
        Panel(help_text, title="[bold]RCM Help[/bold]", border_style="blue")
    )


def _display_config(rcm_app, formatter: ReadableFormatter):
    """Display current configuration"""
    rcm_config = getattr(rcm_app.context.config, "rcm", None)

    config_text = (
        f"""[bold]Configuration Settings:[/bold]

[cyan]Quality Control:[/cyan]
• Quality threshold: {getattr(rcm_config, "quality_threshold", 0.8):.0%}
• Max refinement attempts: {getattr(rcm_config, "max_refinement_attempts", 3)}
• Consolidation interval: {getattr(rcm_config, "consolidation_interval", 3)} turns

[cyan]Display:[/cyan]
• Verbosity: {getattr(rcm_config, "verbosity", "normal")}
• Internal messages: {"visible" if getattr(rcm_config, "show_internal_messages", True) else "hidden"}
• Quality metrics: {"verbose" if getattr(rcm_config, "verbose_metrics", False) else "compact"}

[cyan]Execution:[/cyan]
• Engine: {rcm_app.context.config.execution_engine}
• Model provider: {getattr(rcm_config, "evaluator_model_provider", "openai")}"""
        if rcm_config
        else """[bold]Configuration Settings:[/bold]

[cyan]Using default configuration[/cyan]
• Quality threshold: 80%
• Max refinement attempts: 3
• Consolidation interval: 3 turns"""
    )

    formatter.console.print(
        Panel(config_text, title="[bold]Configuration[/bold]", border_style="green")
    )


def _display_stats_enhanced(state: ConversationState, formatter: ReadableFormatter):
    """Enhanced stats display using formatter"""
    if not state:
        formatter.show_warning("No conversation started yet")
        return

    # Build stats data
    stats = {
        "total_turns": state.current_turn,
        "total_messages": len(state.messages),
        "requirements_tracked": len(state.requirements),
        "consolidation_turns": len(state.consolidation_turns),
    }

    if state.requirements:
        pending = len([r for r in state.requirements if r.status == "pending"])
        addressed = len([r for r in state.requirements if r.status == "addressed"])
        stats["pending_requirements"] = pending
        stats["addressed_requirements"] = addressed

    if state.quality_history:
        avg_quality = sum(q.overall_score for q in state.quality_history) / len(
            state.quality_history
        )
        latest_quality = state.quality_history[-1].overall_score
        stats["average_quality"] = avg_quality
        stats["latest_quality"] = latest_quality

    if state.answer_lengths:
        avg_length = sum(state.answer_lengths) / len(state.answer_lengths)
        stats["avg_response_length"] = f"{avg_length:.0f} chars"

        if len(state.answer_lengths) > 1:
            bloat = state.answer_lengths[-1] / state.answer_lengths[0]
            stats["answer_bloat_ratio"] = f"{bloat:.1f}x"

    # Add research metrics
    if state.first_answer_attempt_turn:
        stats["first_answer_attempt"] = f"Turn {state.first_answer_attempt_turn}"

    formatter.format_conversation_stats(stats)


def _display_requirements_enhanced(
    state: ConversationState, formatter: ReadableFormatter
):
    """Enhanced requirements display using formatter"""
    if not state or not state.requirements:
        formatter.show_warning("No requirements tracked yet")
        return

    # Convert requirements to display format
    requirements_data = [r.to_dict() for r in state.requirements]
    formatter.format_requirements_status(requirements_data)


def _display_final_summary_enhanced(
    state: ConversationState, formatter: ReadableFormatter
):
    """Enhanced final summary using formatter"""
    summary_text = f"""[bold green]Conversation Complete[/bold green]

[bold]Summary:[/bold]
• Total turns: {state.current_turn}
• Messages exchanged: {len(state.messages)}
• Requirements tracked: {len(state.requirements)}
• Context consolidations: {len(state.consolidation_turns)}

[bold]Quality Performance:[/bold]"""

    if state.quality_history:
        avg_quality = sum(q.overall_score for q in state.quality_history) / len(
            state.quality_history
        )
        summary_text += f"\n• Average quality score: {avg_quality:.0%}"

        # Quality trend
        first_quality = state.quality_history[0].overall_score
        last_quality = state.quality_history[-1].overall_score
        trend = (
            "improved"
            if last_quality > first_quality
            else "maintained"
            if last_quality == first_quality
            else "declined"
        )
        summary_text += f"\n• Quality trend: {trend}"

    if state.answer_lengths and len(state.answer_lengths) > 1:
        bloat = state.answer_lengths[-1] / state.answer_lengths[0]
        bloat_status = (
            "minimal" if bloat < 1.5 else "moderate" if bloat < 2.0 else "significant"
        )
        summary_text += f"\n• Answer bloat: {bloat:.1f}x ({bloat_status})"

    summary_text += f"\n\n[dim]Conversation ID: {state.conversation_id}[/dim]"

    formatter.console.print(
        Panel(summary_text, title="[bold]Session Complete[/bold]", border_style="green")
    )


def _display_quality_metrics(metrics: dict):
    """Display quality metrics in a table"""
    if not metrics:
        return

    table = Table(title="Response Quality Metrics", show_header=False)
    table.add_column("Metric", style="cyan")
    table.add_column("Score", style="green")

    for key, value in metrics.items():
        if key not in ["issues", "overall_score"]:  # Skip nested objects
            display_value = f"{value:.2f}" if isinstance(value, float) else str(value)
            table.add_row(key.replace("_", " ").title(), display_value)

    if "overall_score" in metrics:
        table.add_row("Overall Score", f"{metrics['overall_score']:.2f}")

    console.print(table)


def _display_stats(state: ConversationState):
    """Display conversation statistics"""
    if not state:
        console.print("[yellow]No conversation started yet[/yellow]")
        return

    table = Table(title="Conversation Statistics")
    table.add_column("Metric", style="cyan")
    table.add_column("Value", style="green")

    table.add_row("Total Turns", str(state.current_turn))
    table.add_row("Messages", str(len(state.messages)))
    table.add_row("Requirements Tracked", str(len(state.requirements)))

    if state.requirements:
        pending = len([r for r in state.requirements if r.status == "pending"])
        table.add_row("Pending Requirements", str(pending))

    if state.quality_history:
        avg_quality = sum(q.overall_score for q in state.quality_history) / len(
            state.quality_history
        )
        table.add_row("Average Quality Score", f"{avg_quality:.2f}")

    if state.answer_lengths:
        avg_length = sum(state.answer_lengths) / len(state.answer_lengths)
        table.add_row("Avg Response Length", f"{avg_length:.0f} chars")

        # Check for bloat
        if len(state.answer_lengths) > 2:
            bloat = state.answer_lengths[-1] / state.answer_lengths[0]
            color = "red" if bloat > 2.0 else "yellow" if bloat > 1.5 else "green"
            table.add_row("Response Bloat Ratio", f"[{color}]{bloat:.1f}x[/{color}]")

    console.print(table)


def _display_requirements(state: ConversationState):
    """Display tracked requirements"""
    if not state or not state.requirements:
        console.print("[yellow]No requirements tracked yet[/yellow]")
        return

    table = Table(title="Tracked Requirements")
    table.add_column("ID", style="cyan")
    table.add_column("Description", style="white")
    table.add_column("Status", style="green")
    table.add_column("Turn", style="blue")

    for req in state.requirements:
        status_color = {
            "pending": "yellow",
            "addressed": "blue",
            "confirmed": "green",
        }.get(req.status, "white")

        table.add_row(
            req.id[:8],  # Show first 8 chars of ID
            req.description[:50] + "..."
            if len(req.description) > 50
            else req.description,
            f"[{status_color}]{req.status}[/{status_color}]",
            str(req.source_turn),
        )

    console.print(table)


def _display_final_summary(state: ConversationState):
    """Display final conversation summary"""
    console.print(
        Panel.fit(
            f"[bold green]Conversation Summary[/bold green]\n\n"
            f"Total turns: {state.current_turn}\n"
            f"Messages exchanged: {len(state.messages)}\n"
            f"Requirements tracked: {len(state.requirements)}\n"
            f"Conversation ID: {state.conversation_id}",
            border_style="green",
        )
    )


if __name__ == "__main__":
    start = time.time()
    asyncio.run(run_repl())
    end = time.time()
    console.print(f"\nTotal runtime: {end - start:.2f}s")
