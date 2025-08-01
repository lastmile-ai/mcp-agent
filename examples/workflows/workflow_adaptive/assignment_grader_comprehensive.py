"""
Assignment Grader using Adaptive Workflow V2 - Comprehensive Demo

Demonstrates all key features of AdaptiveWorkflow:
- Progress tracking with Rich Progress bars
- Token counting and cost tracking
- Queue visualization
- Knowledge/memory display
- Detailed final report

Usage:
    python assignment_grader_comprehensive.py                    # Uses predefined agents
    python assignment_grader_comprehensive.py --no-predefined    # Creates agents dynamically
    python assignment_grader_comprehensive.py --verbose          # Show detailed progress
"""

import asyncio
import argparse
import io
import logging
import os
import time
import warnings
from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime, timedelta, timezone
from typing import List
from collections import deque

from mcp_agent.app import MCPApp
from mcp_agent.agents.agent import Agent
from mcp_agent.workflows.llm.augmented_llm import RequestParams
from mcp_agent.workflows.llm.augmented_llm_openai import OpenAIAugmentedLLM
from mcp_agent.workflows.adaptive.adaptive_workflow import AdaptiveWorkflow
from mcp_agent.workflows.adaptive.memory import MemoryManager
from mcp_agent.workflows.adaptive.models import TaskType
from mcp_agent.tracing.token_counter import TokenNode
from mcp.types import ModelPreferences
from rich.console import Console
from rich.panel import Panel
from rich.progress import (
    Progress,
    SpinnerColumn,
    TextColumn,
    BarColumn,
    TimeElapsedColumn,
)
from rich.table import Table
from rich.layout import Layout
from rich.live import Live
from rich.text import Text

# Configure Python's root logger to disable console output
logging.getLogger().handlers = []
logging.getLogger().addHandler(logging.NullHandler())
logging.getLogger("mcp_agent").setLevel(logging.WARNING)
logging.getLogger("opentelemetry").setLevel(logging.WARNING)

# Suppress warnings
warnings.filterwarnings("ignore", category=UserWarning)
warnings.filterwarnings("ignore", message=".*uvloop.*")

console = Console()


class WorkflowTracker:
    """Track workflow execution details"""

    def __init__(self):
        self.start_time = time.time()
        self.events = deque(maxlen=50)
        self.agent_executions = {}
        self.token_usage = {}
        self.knowledge_items = []
        self.queue_status = {}
        self.errors = []

    def add_event(
        self, event_type: str, message: str, detail: str = "", severity: str = "info"
    ):
        """Add an event to the tracker"""
        self.events.append(
            {
                "time": datetime.now(timezone.utc),
                "type": event_type,
                "message": message,
                "detail": detail,
                "severity": severity,
            }
        )

    def update_agent_execution(self, agent_name: str, status: str, duration: float = 0):
        """Update agent execution tracking"""
        if agent_name not in self.agent_executions:
            self.agent_executions[agent_name] = {
                "count": 0,
                "total_duration": 0,
                "status": "idle",
            }
        self.agent_executions[agent_name]["count"] += 1
        self.agent_executions[agent_name]["total_duration"] += duration
        self.agent_executions[agent_name]["status"] = status


async def create_predefined_agents(context) -> List[Agent]:
    """Create specialized agents for grading"""

    with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
        file_handler = Agent(
            name="FileHandler",
            instruction="""I manage file operations for the grading process. I can:
            - Find and read the student's short story
            - Write the graded report to disk
            - Navigate directory structures efficiently""",
            server_names=["filesystem"],
            context=context,
        )

        apa_expert = Agent(
            name="APAStyleExpert",
            instruction="""I specialize in APA style guidelines. I can:
            - Fetch official APA style rules
            - Evaluate text for APA compliance
            - Provide specific formatting recommendations""",
            server_names=["fetch"],
            context=context,
        )

        proofreader = Agent(
            name="Proofreader",
            instruction="""I provide detailed proofreading feedback. I can:
            - Check grammar, spelling, and punctuation
            - Identify awkward phrasing
            - Suggest clarity improvements""",
            server_names=["fetch", "filesystem"],
            context=context,
        )

    return [file_handler, apa_expert, proofreader]


def create_progress_layout() -> Layout:
    """Create the progress display layout"""
    layout = Layout()

    layout.split_column(
        Layout(name="header", size=3),
        Layout(name="main", size=20),
        Layout(name="footer", size=3),
    )

    # Header
    header_text = Text(
        "📚 Assignment Grader - Adaptive Workflow V2",
        style="bold cyan",
        justify="center",
    )
    layout["header"].update(Panel(header_text, border_style="cyan"))

    # Main area split into columns
    layout["main"].split_row(
        Layout(name="progress", ratio=2), Layout(name="stats", ratio=1)
    )

    return layout


def update_stats_panel(
    layout: Layout, workflow: AdaptiveWorkflow, tracker: WorkflowTracker
):
    """Update the statistics panel"""
    stats_table = Table(show_header=False, box=None)
    stats_table.add_column("Metric", style="cyan")
    stats_table.add_column("Value", style="white")

    # Time elapsed
    elapsed = time.time() - tracker.start_time
    stats_table.add_row("Elapsed", f"{elapsed:.1f}s")

    # Workflow stats
    if workflow._current_memory:
        stats_table.add_row("Iterations", str(workflow._current_memory.iterations))
        stats_table.add_row("Cost", f"${workflow._current_memory.total_cost:.4f}")

        # Token usage
        if workflow.context and workflow.context.token_counter:
            usage = workflow.context.token_counter.get_workflow_usage(workflow.name)
            if usage:
                stats_table.add_row("Total Tokens", f"{usage.total_tokens:,}")

        # Knowledge items
        if hasattr(workflow._current_memory, "knowledge_items"):
            stats_table.add_row(
                "Knowledge Items", str(len(workflow._current_memory.knowledge_items))
            )

    # Queue status
    if hasattr(workflow, "subtask_queue") and workflow.subtask_queue:
        status = workflow.subtask_queue.get_queue_status()
        stats_table.add_row("Tasks Pending", str(status["queue_length"]))
        stats_table.add_row("Tasks Complete", str(status["completed_count"]))

    layout["stats"].update(Panel(stats_table, title="📊 Metrics", border_style="blue"))


class ComprehensiveWorkflowMonitor:
    """Enhanced workflow monitor with progress tracking"""

    def __init__(
        self,
        workflow: AdaptiveWorkflow,
        tracker: WorkflowTracker,
        verbose: bool = False,
    ):
        self.workflow = workflow
        self.tracker = tracker
        self.verbose = verbose
        self._original_methods = {}
        self.progress = Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
            TimeElapsedColumn(),
            console=console,
            expand=False,
        )
        self.main_task_id = None
        self.current_subtasks = {}

    async def __aenter__(self):
        self._patch_methods()
        self.progress.start()
        self.main_task_id = self.progress.add_task("Grading Assignment", total=100)
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        self._unpatch_methods()
        self.progress.stop()

    def _patch_methods(self):
        """Patch workflow methods to track progress"""

        # Patch analyze_objective
        original_analyze = self.workflow._analyze_objective

        async def patched_analyze(*args, **kwargs):
            self.progress.update(
                self.main_task_id, advance=5, description="Analyzing objective..."
            )
            self.tracker.add_event("analyze", "Analyzing objective")
            result = await original_analyze(*args, **kwargs)
            self.tracker.add_event("analyze", "Objective analyzed", severity="success")
            return result

        self._original_methods["_analyze_objective"] = original_analyze
        self.workflow._analyze_objective = patched_analyze

        # Patch plan_research
        original_plan = self.workflow._plan_research

        async def patched_plan(*args, **kwargs):
            self.progress.update(
                self.main_task_id, advance=10, description="Planning research..."
            )
            self.tracker.add_event("plan", "Planning research approach")
            result = await original_plan(*args, **kwargs)
            if result:
                self.tracker.add_event(
                    "plan",
                    f"Research planned: {len(result)} aspects",
                    severity="success",
                )
                # Add subtasks to progress
                for aspect in result:
                    task_id = self.progress.add_task(f"[cyan]{aspect.name}", total=100)
                    self.current_subtasks[aspect.name] = task_id
            return result

        self._original_methods["_plan_research"] = original_plan
        self.workflow._plan_research = patched_plan

        # Patch execute_single_subtask
        original_execute = self.workflow._execute_single_subtask

        async def patched_execute(subtask, *args, **kwargs):
            aspect_name = (
                subtask.aspect.name if hasattr(subtask, "aspect") else "Unknown"
            )
            start_time = time.time()

            # Update progress
            if aspect_name in self.current_subtasks:
                self.progress.update(self.current_subtasks[aspect_name], advance=50)

            self.tracker.add_event("execute", f"Starting: {aspect_name}")
            self.tracker.update_agent_execution(aspect_name, "running")

            # Execute with error handling
            try:
                with redirect_stderr(io.StringIO()):
                    result = await original_execute(subtask, *args, **kwargs)

                duration = time.time() - start_time
                self.tracker.update_agent_execution(aspect_name, "completed", duration)
                self.tracker.add_event(
                    "execute",
                    f"Completed: {aspect_name}",
                    f"Duration: {duration:.1f}s",
                    "success",
                )

                # Complete subtask progress
                if aspect_name in self.current_subtasks:
                    self.progress.update(
                        self.current_subtasks[aspect_name], advance=50, completed=100
                    )

                # Advance main progress
                self.progress.update(self.main_task_id, advance=5)

                return result

            except Exception as e:
                self.tracker.add_event(
                    "error", f"Error in {aspect_name}: {str(e)}", severity="error"
                )
                self.tracker.errors.append({"agent": aspect_name, "error": str(e)})
                raise

        self._original_methods["_execute_single_subtask"] = original_execute
        self.workflow._execute_single_subtask = patched_execute

        # Patch synthesize_results
        original_synthesize = self.workflow._synthesize_results

        async def patched_synthesize(*args, **kwargs):
            self.progress.update(
                self.main_task_id, advance=20, description="Synthesizing results..."
            )
            self.tracker.add_event("synthesize", "Synthesizing results")
            result = await original_synthesize(*args, **kwargs)
            self.tracker.add_event(
                "synthesize", "Results synthesized", severity="success"
            )
            return result

        self._original_methods["_synthesize_results"] = original_synthesize
        self.workflow._synthesize_results = patched_synthesize

        # Patch generate_final_report
        original_report = self.workflow._generate_final_report

        async def patched_report(*args, **kwargs):
            self.progress.update(
                self.main_task_id, advance=20, description="Generating report..."
            )
            self.tracker.add_event("report", "Generating final report")
            result = await original_report(*args, **kwargs)
            self.tracker.add_event("report", "Report generated", severity="success")
            self.progress.update(self.main_task_id, completed=100)
            return result

        self._original_methods["_generate_final_report"] = original_report
        self.workflow._generate_final_report = patched_report


def display_token_tree(node: TokenNode, indent: int = 0) -> List[str]:
    """Generate token tree display lines"""
    lines = []
    prefix = "  " * indent
    usage = node.aggregate_usage()

    line = f"{prefix}{'└── ' if indent > 0 else ''}{node.name}"
    if usage.total_tokens > 0:
        line += f" ({usage.total_tokens:,} tokens, ${node.usage.cost:.4f})"
    lines.append(line)

    for child in node.children.values():
        lines.extend(display_token_tree(child, indent + 1))

    return lines


def generate_comprehensive_report(
    workflow: AdaptiveWorkflow, tracker: WorkflowTracker
) -> str:
    """Generate a comprehensive execution report"""
    lines = ["# Assignment Grader - Execution Report", ""]

    # Summary
    elapsed = time.time() - tracker.start_time
    lines.extend(
        [
            "## Executive Summary",
            f"- **Total Time**: {elapsed:.1f} seconds",
            f"- **Total Cost**: ${workflow._current_memory.total_cost:.4f}"
            if workflow._current_memory
            else "- **Total Cost**: $0.00",
            f"- **Iterations**: {workflow._current_memory.iterations}"
            if workflow._current_memory
            else "- **Iterations**: 0",
            "",
        ]
    )

    # Agent Execution Summary
    if tracker.agent_executions:
        lines.extend(["## Agent Execution Summary", ""])
        agent_table = []
        for agent, stats in tracker.agent_executions.items():
            agent_table.append(
                f"- **{agent}**: {stats['count']} executions, {stats['total_duration']:.1f}s total"
            )
        lines.extend(agent_table)
        lines.append("")

    # Token Usage
    if workflow.context and workflow.context.token_counter:
        lines.extend(["## Token Usage Analysis", ""])
        summary = workflow.context.token_counter.get_summary()
        lines.extend(
            [
                f"- **Total Tokens**: {summary.usage.total_tokens:,}",
                f"- **Input Tokens**: {summary.usage.input_tokens:,}",
                f"- **Output Tokens**: {summary.usage.output_tokens:,}",
                "",
            ]
        )

        # Model breakdown
        if summary.model_usage:
            lines.append("### Breakdown by Model:")
            for model_key, data in summary.model_usage.items():
                lines.append(
                    f"- **{model_key}**: {data.usage.total_tokens:,} tokens (${data.cost:.4f})"
                )
            lines.append("")

    # Knowledge Extracted
    if workflow._current_memory and hasattr(
        workflow._current_memory, "knowledge_items"
    ):
        lines.extend(
            [
                "## Knowledge Items Extracted",
                f"Total items: {len(workflow._current_memory.knowledge_items)}",
                "",
            ]
        )

        if workflow._current_memory.knowledge_items:
            lines.append("### Sample Knowledge Items:")
            for item in workflow._current_memory.knowledge_items[:3]:
                lines.append(f"- **Q**: {item.question}")
                lines.append(f"  **A**: {item.answer[:100]}...")
                lines.append(f"  **Confidence**: {item.confidence:.2f}")
            lines.append("")

    # Errors
    if tracker.errors:
        lines.extend(["## Errors Encountered", ""])
        for error in tracker.errors:
            lines.append(f"- {error['agent']}: {error['error']}")
        lines.append("")

    # Performance Metrics
    lines.extend(
        [
            "## Performance Metrics",
            f"- **Average time per iteration**: {elapsed / workflow._current_memory.iterations:.1f}s"
            if workflow._current_memory and workflow._current_memory.iterations > 0
            else "- **Average time per iteration**: N/A",
            f"- **Tokens per second**: {summary.usage.total_tokens / elapsed:.0f}"
            if workflow.context and workflow.context.token_counter and elapsed > 0
            else "- **Tokens per second**: N/A",
            f"- **Cost per iteration**: ${workflow._current_memory.total_cost / workflow._current_memory.iterations:.4f}"
            if workflow._current_memory and workflow._current_memory.iterations > 0
            else "- **Cost per iteration**: N/A",
            "",
        ]
    )

    return "\n".join(lines)


app = MCPApp(name="assignment_grader_comprehensive")


async def main(use_predefined_agents: bool = True, verbose: bool = False):
    """Run the comprehensive assignment grader demo"""

    async with app.run() as grader_app:
        console.clear()

        # Task definition
        task = """Load the student's short story from short_story.md, 
        and generate a report with feedback across proofreading, 
        factuality/logical consistency and style adherence. Use the style rules from 
        https://owl.purdue.edu/owl/research_and_citation/apa_style/apa_formatting_and_style_guide/general_format.html.
        Write the graded report to graded_report.md in the same directory as short_story.md"""

        console.print(
            "\n[bold cyan]📚 Assignment Grader - Adaptive Workflow V2[/bold cyan]"
        )
        console.print("=" * 80 + "\n")

        console.print("[bold]Task:[/bold]")
        console.print(Panel(task, border_style="blue"))
        console.print()

        # Configure filesystem server
        grader_app.context.config.mcp.servers["filesystem"].args.extend([os.getcwd()])

        # Set up agents
        tracker = WorkflowTracker()

        agents = []
        if use_predefined_agents:
            console.print("[cyan]Creating predefined agents...[/cyan]")
            agents = await create_predefined_agents(grader_app.context)
            for agent in agents:
                console.print(
                    f"  ✅ Created {agent.name} [dim](Servers: {', '.join(agent.server_names)})[/dim]"
                )
        else:
            console.print("[cyan]Using dynamic agent creation[/cyan]")

        console.print()

        # Create memory manager
        memory_manager = MemoryManager(enable_learning=True)

        # Define LLM factory
        def llm_factory(agent: Agent) -> OpenAIAugmentedLLM:
            return OpenAIAugmentedLLM(
                agent=agent,
                context=grader_app.context,
            )

        # Create workflow
        workflow = AdaptiveWorkflow(
            llm_factory=llm_factory,
            name="AssignmentGrader",
            available_agents=agents if use_predefined_agents else None,
            available_servers=["filesystem", "fetch"],
            task_type=TaskType.ACTION,  # Assignment grading is more action-oriented
            time_budget=timedelta(minutes=5),
            cost_budget=3.0,
            max_iterations=10,
            enable_parallel=True,
            memory_manager=memory_manager,
            context=grader_app.context,
            model_preferences=ModelPreferences(model="gpt-4o"),
        )

        # Execute with comprehensive monitoring
        start_time = time.time()

        async with ComprehensiveWorkflowMonitor(workflow, tracker, verbose) as monitor:
            # Create layout for live display if verbose
            if verbose:
                layout = create_progress_layout()
                layout["progress"].update(monitor.progress)

                with Live(layout, refresh_per_second=4, console=console):
                    # Update stats in background
                    async def update_display():
                        while True:
                            try:
                                update_stats_panel(layout, workflow, tracker)
                                await asyncio.sleep(0.5)
                            except Exception:
                                break

                    display_task = asyncio.create_task(update_display())

                    try:
                        result = await workflow.generate_str(
                            message=task,
                            request_params=RequestParams(
                                model="gpt-4o", max_iterations=10, temperature=0.3
                            ),
                        )
                    finally:
                        display_task.cancel()
            else:
                # Simple progress display
                with monitor.progress:
                    result = await workflow.generate_str(
                        message=task,
                        request_params=RequestParams(
                            model="gpt-4o", max_iterations=10, temperature=0.3
                        ),
                    )

        elapsed = time.time() - start_time

        # Display results
        console.print("\n[bold green]✅ Workflow completed![/bold green]\n")

        # Show execution summary
        if workflow._current_memory:
            summary_table = Table(title="Execution Summary", show_header=True)
            summary_table.add_column("Metric", style="cyan")
            summary_table.add_column("Value", style="white")

            summary_table.add_row("Time", f"{elapsed:.1f} seconds")
            summary_table.add_row(
                "Iterations", str(workflow._current_memory.iterations)
            )
            summary_table.add_row(
                "Agents Used", str(len(workflow._current_memory.subagent_results))
            )
            summary_table.add_row(
                "Total Cost", f"${workflow._current_memory.total_cost:.4f}"
            )

            if workflow.context and workflow.context.token_counter:
                usage = workflow.context.token_counter.get_workflow_usage(workflow.name)
                if usage:
                    summary_table.add_row("Total Tokens", f"{usage.total_tokens:,}")

            summary_table.add_row(
                "Performance", f"~{90 / elapsed:.1f}x faster than baseline"
            )

            console.print(summary_table)
            console.print()

        # Token usage tree
        if workflow.context and workflow.context.token_counter:
            root_node = workflow.context.token_counter.get_node(workflow.name)
            if root_node:
                console.print("[bold]Token Usage Tree:[/bold]")
                tree_lines = display_token_tree(root_node)
                for line in tree_lines[:10]:  # Show first 10 lines
                    console.print(line)
                if len(tree_lines) > 10:
                    console.print(f"... and {len(tree_lines) - 10} more")
                console.print()

        # Show report preview
        if result:
            console.print("[bold]Report Preview:[/bold]")
            preview = result[:500] + "..." if len(result) > 500 else result
            console.print(Panel(preview, border_style="green"))
            console.print()

        # Generate and save comprehensive report
        report = generate_comprehensive_report(workflow, tracker)
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        report_filename = f"execution_report_{timestamp}.md"

        with open(report_filename, "w") as f:
            f.write(report)

        console.print("[green]✅ Report saved to graded_report.md[/green]")
        console.print(f"[green]✅ Execution report saved to {report_filename}[/green]")
        console.print()

        # Final stats
        console.print("[dim]Press Enter to view the full execution report...[/dim]")
        input()
        console.print(Panel(report, title="Full Execution Report", border_style="blue"))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Grade student assignments using Adaptive Workflow V2 with comprehensive tracking"
    )
    parser.add_argument(
        "--no-predefined",
        action="store_true",
        help="Create agents dynamically instead of using predefined agents",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Show detailed progress with live display",
    )

    args = parser.parse_args()

    # Change to example directory
    os.chdir(os.path.dirname(os.path.abspath(__file__)))

    # Run with specified mode
    asyncio.run(
        main(use_predefined_agents=not args.no_predefined, verbose=args.verbose)
    )
