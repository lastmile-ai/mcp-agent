#!/usr/bin/env python
"""
Deep Orchestrator Example - Assignment Grader with Full State Visibility

This example demonstrates the Deep Orchestrator (AdaptiveOrchestrator) with:
- Dynamic agent creation and caching
- Knowledge extraction and accumulation
- Budget tracking (tokens, cost, time)
- Task queue management with dependencies
- Policy-driven execution control
- Full state visibility throughout execution
"""

import asyncio
import os
import time
from datetime import datetime

from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.tree import Tree
from rich.live import Live
from rich.layout import Layout
from rich.columns import Columns
from rich import box

from mcp_agent.app import MCPApp
from mcp_agent.agents.agent import Agent
from mcp_agent.workflows.deep_orchestrator.orchestrator import DeepOrchestrator
from mcp_agent.workflows.deep_orchestrator.config import (
    DeepOrchestratorConfig,
    ExecutionConfig,
    BudgetConfig,
)
from mcp_agent.workflows.llm.augmented_llm_openai import OpenAIAugmentedLLM
from mcp_agent.workflows.llm.augmented_llm import RequestParams

console = Console()


class DeepOrchestratorMonitor:
    """Monitor to expose all internal state of the Deep Orchestrator"""

    def __init__(self, orchestrator: DeepOrchestrator):
        self.orchestrator = orchestrator
        self.start_time = time.time()

    def get_budget_table(self) -> Table:
        """Get budget status as a table"""
        budget = self.orchestrator.budget
        usage = budget.get_usage_pct()
        budget.get_remaining()

        table = Table(title="💰 Budget", box=box.ROUNDED, show_header=True)
        table.add_column("Resource", style="cyan")
        table.add_column("Used", style="yellow")
        table.add_column("Limit", style="green")
        table.add_column("Usage %", style="magenta")

        # Tokens
        table.add_row(
            "Tokens",
            f"{budget.tokens_used:,}",
            f"{budget.max_tokens:,}",
            f"{usage['tokens']:.1%}",
        )

        # Cost
        table.add_row(
            "Cost",
            f"${budget.cost_incurred:.3f}",
            f"${budget.max_cost:.2f}",
            f"{usage['cost']:.1%}",
        )

        # Time
        elapsed = datetime.now(budget.start_time.tzinfo) - budget.start_time
        elapsed_minutes = elapsed.total_seconds() / 60
        table.add_row(
            "Time",
            f"{elapsed_minutes:.1f} min",
            f"{budget.max_time_minutes} min",
            f"{usage['time']:.1%}",
        )

        return table

    def get_queue_tree(self) -> Tree:
        """Get task queue as a tree"""
        queue = self.orchestrator.queue
        tree = Tree("📋 Task Queue")

        # Completed steps
        if queue.completed_steps:
            completed = tree.add("[green]✅ Completed Steps")
            for step in queue.completed_steps[-2:]:  # Last 2 steps only
                step_node = completed.add(f"[dim]{step.description[:60]}...")
                # Show first 3 tasks if many, otherwise all
                tasks_to_show = step.tasks[:3] if len(step.tasks) > 3 else step.tasks
                for task in tasks_to_show:
                    if task.status == "completed":
                        icon = "[green]✓[/green]"
                    elif task.status == "failed":
                        icon = "[red]✗[/red]"
                    else:
                        icon = "•"
                    step_node.add(f"[dim]{icon} {task.description[:40]}...")
                if len(step.tasks) > 3:
                    step_node.add(f"[dim italic]... +{len(step.tasks) - 3} more tasks")

        # Current/Active step - prioritize showing active and failed tasks
        current_step = queue.get_next_step()
        if current_step:
            active = tree.add("[yellow]▶ Active Step")
            active_node = active.add(f"[yellow]{current_step.description[:60]}...")

            # Sort tasks to prioritize: in_progress > failed > pending > completed
            def task_priority(task):
                priorities = {
                    "in_progress": 0,
                    "failed": 1,
                    "pending": 2,
                    "completed": 3,
                }
                return priorities.get(task.status, 4)

            sorted_tasks = sorted(current_step.tasks, key=task_priority)
            tasks_to_show = sorted_tasks[:5]  # Show up to 5 for active step

            for task in tasks_to_show:
                if task.status == "in_progress":
                    icon = "[yellow]⟳[/yellow]"
                elif task.status == "failed":
                    icon = "[red]✗[/red]"
                elif task.status == "completed":
                    icon = "[green]✓[/green]"
                else:
                    icon = "•"
                active_node.add(f"{icon} {task.description[:40]}...")

            # Show remaining count with status breakdown if needed
            remaining = len(current_step.tasks) - len(tasks_to_show)
            if remaining > 0:
                # Count by status for the remaining tasks
                status_counts = {}
                for task in sorted_tasks[4:]:
                    status_counts[task.status] = status_counts.get(task.status, 0) + 1

                if status_counts:
                    parts = []
                    if status_counts.get("pending", 0) > 0:
                        parts.append(f"{status_counts['pending']} pending")
                    if status_counts.get("completed", 0) > 0:
                        parts.append(f"{status_counts['completed']} done")
                    active_node.add(
                        f"[dim italic]... +{remaining} more ({', '.join(parts)})"
                    )

        # Pending steps (just count)
        if queue.pending_steps:
            _pending = tree.add(f"[dim]⏳ {len(queue.pending_steps)} Pending Steps")

        # Failed tasks summary if any
        if queue.failed_task_names:
            failed = tree.add(f"[red]❌ {len(queue.failed_task_names)} Failed Tasks")
            for task_name in list(queue.failed_task_names)[:2]:
                failed.add(f"[red dim]{task_name}")

        # Queue summary
        tree.add(f"[blue]📊 {queue.get_progress_summary()}")

        return tree

    def get_plan_table(self) -> Table:
        """Get the current plan as a table"""
        table = Table(title="📝 Current Plan", box=box.ROUNDED, show_header=True)
        table.add_column("Step", style="cyan", width=3)
        table.add_column("Description", style="yellow")
        table.add_column("Tasks", style="green", width=3)
        table.add_column("Status", style="magenta", width=10)

        if (
            not hasattr(self.orchestrator, "current_plan")
            or not self.orchestrator.current_plan
        ):
            table.add_row("-", "No plan created yet", "-", "-")
            return table

        plan = self.orchestrator.current_plan
        queue = self.orchestrator.queue

        for i, step in enumerate(plan.steps, 1):
            # Determine status
            if step in queue.completed_steps:
                status = "[green]✓ Done[/green]"
            elif step == queue.get_next_step():
                status = "[yellow]→ Active[/yellow]"
            else:
                status = "[dim]Pending[/dim]"

            table.add_row(
                str(i),
                step.description[:60] + "..."
                if len(step.description) > 60
                else step.description,
                str(len(step.tasks)),
                status,
            )

        return table

    async def get_token_stats_panel(self) -> Panel:
        """Get token usage statistics"""
        lines = []

        # Get token breakdown from context if available
        if self.orchestrator.context and hasattr(
            self.orchestrator.context, "token_counter"
        ):
            counter = self.orchestrator.context.token_counter
            if counter:
                # Get summary
                summary = await counter.get_summary()
                if summary and hasattr(summary, "usage"):
                    usage = summary.usage
                    lines.append(f"[cyan]Total Tokens:[/cyan] {usage.total_tokens:,}")
                    lines.append(f"[cyan]Input Tokens:[/cyan] {usage.input_tokens:,}")
                    lines.append(f"[cyan]Output Tokens:[/cyan] {usage.output_tokens:,}")

                    # Cost if available
                    if hasattr(summary, "cost"):
                        lines.append(
                            f"[cyan]Estimated Cost:[/cyan] ${summary.cost:.4f}"
                        )

                    # Get top consumers
                    node = await counter.find_node(self.orchestrator.name)
                    if node and node.children:
                        lines.append("\n[yellow]Top Consumers:[/yellow]")
                        sorted_children = sorted(
                            node.children,
                            key=lambda n: n.usage.total_tokens,
                            reverse=True,
                        )
                        for child in sorted_children[:3]:
                            pct = (
                                (child.usage.total_tokens / usage.total_tokens * 100)
                                if usage.total_tokens > 0
                                else 0
                            )
                            lines.append(
                                f"  • {child.name[:30]}: {child.usage.total_tokens:,} ({pct:.1f}%)"
                            )

        if not lines:
            lines.append("[dim]No token usage data available yet[/dim]")

        return Panel("\n".join(lines), title="📊 Token Usage", border_style="blue")

    def get_memory_panel(self) -> Panel:
        """Get memory status as a panel"""
        memory = self.orchestrator.memory
        stats = memory.get_stats()

        lines = [
            f"[cyan]Artifacts:[/cyan] {stats['artifacts']}",
            f"[cyan]Knowledge Items:[/cyan] {stats['knowledge_items']}",
            f"[cyan]Task Results:[/cyan] {stats['task_results']}",
            f"[cyan]Categories:[/cyan] {stats['knowledge_categories']}",
            f"[cyan]Est. Tokens:[/cyan] {stats['estimated_tokens']:,}",
        ]

        # Add recent knowledge items
        if memory.knowledge:
            lines.append("\n[yellow]Recent Knowledge:[/yellow]")
            for item in memory.knowledge[-3:]:
                lines.append(f"  • {item.key[:40]}: {str(item.value)[:40]}...")

        content = "\n".join(lines)
        return Panel(content, title="🧠 Memory", border_style="blue")

    def get_agents_table(self) -> Table:
        """Get agent cache status"""
        cache = self.orchestrator.agent_cache

        table = Table(title="🤖 Agent Cache", box=box.SIMPLE)
        table.add_column("Metric", style="cyan")
        table.add_column("Value", style="green")

        table.add_row("Cached Agents", str(len(cache.cache)))
        table.add_row("Cache Hits", str(cache.hits))
        table.add_row("Cache Misses", str(cache.misses))

        if cache.hits + cache.misses > 0:
            hit_rate = cache.hits / (cache.hits + cache.misses)
            table.add_row("Hit Rate", f"{hit_rate:.1%}")

        # Show cached agent names
        if cache.cache:
            agent_names = []
            for key, agent in list(cache.cache.items())[:3]:
                agent_names.append(agent.name)
            if agent_names:
                table.add_row("Recent", ", ".join(agent_names))

        return table

    def get_policy_panel(self) -> Panel:
        """Get policy engine status"""
        policy = self.orchestrator.policy

        lines = [
            f"[cyan]Consecutive Failures:[/cyan] {policy.consecutive_failures}/{policy.max_consecutive_failures}",
            f"[cyan]Total Successes:[/cyan] {policy.total_successes}",
            f"[cyan]Total Failures:[/cyan] {policy.total_failures}",
            f"[cyan]Failure Rate:[/cyan] {policy.get_failure_rate():.1%}",
        ]

        return Panel("\n".join(lines), title="⚙️ Policy Engine", border_style="yellow")

    def get_status_summary(self) -> Panel:
        """Get overall status summary"""
        elapsed = time.time() - self.start_time

        lines = [
            f"[cyan]Objective:[/cyan]\n        {self.orchestrator.objective[:100]}...",
            f"[cyan]Iteration:[/cyan] {self.orchestrator.iteration}/{self.orchestrator.config.execution.max_iterations}",
            f"[cyan]Replans:[/cyan] {self.orchestrator.replan_count}/{self.orchestrator.config.execution.max_replans}",
            f"[cyan]Elapsed:[/cyan] {elapsed:.1f}s",
        ]

        return Panel("\n".join(lines), title="📊 Status", border_style="green")


def create_display_layout() -> Layout:
    """Create the display layout"""
    layout = Layout()

    # Main structure
    layout.split_column(
        Layout(name="header", size=3),
        Layout(name="top_section", size=12),
        Layout(name="buffer", size=6),
        Layout(name="bottom_section", size=10),
    )

    # Top section - queue, plan, and memory
    layout["top_section"].split_row(
        Layout(name="queue", ratio=3),  # More space for queue/plan
        Layout(name="memory", ratio=2),  # Less for memory
    )

    # Bottom section - budget, status, and agents
    layout["bottom_section"].split_row(
        Layout(name="left", ratio=1),
        Layout(name="center", ratio=1),
        Layout(name="right", ratio=1),
    )

    return layout


def update_display(layout: Layout, monitor: DeepOrchestratorMonitor):
    """Update the display with current state"""

    # Header
    layout["header"].update(
        Panel("🚀 Deep Orchestrator - Assignment Grader", style="bold blue")
    )

    layout["buffer"].update("")

    # Top section - Queue and Plan side by side
    queue_plan_content = Columns(
        [monitor.get_queue_tree(), monitor.get_plan_table()],
        padding=(1, 2),  # Add padding between columns
    )
    layout["queue"].update(queue_plan_content)

    # Memory section
    layout["memory"].update(monitor.get_memory_panel())

    # Bottom section
    # Left column - Budget
    layout["left"].update(monitor.get_budget_table())

    # Center column - Status
    layout["center"].update(monitor.get_status_summary())

    # Right column - Combined Policy and Agents in a vertical layout
    right_content = Layout()
    right_content.split_column(
        Layout(monitor.get_policy_panel(), size=7),
        Layout(monitor.get_agents_table(), size=10),
    )
    layout["right"].update(right_content)


async def main():
    """Run the Deep Orchestrator example"""

    # Initialize MCP App
    app = MCPApp(name="deep_orchestrator_example")

    async with app.run() as mcp_app:
        context = mcp_app.context
        logger = mcp_app.logger

        # Configure filesystem server with current directory
        context.config.mcp.servers["filesystem"].args.extend([os.getcwd()])

        console.print("\n[bold cyan]🚀 Deep Orchestrator Example[/bold cyan]")
        console.print(
            "This demonstrates all the advanced features with full state visibility\n"
        )

        # Create some predefined agents (optional - orchestrator can create its own)
        _predefined_agents = [
            Agent(
                name="FileExpert",
                instruction="""I specialize in file operations and content management.
                I can read, write, and analyze files efficiently.""",
                server_names=["filesystem"],
                context=context,
            ),
            Agent(
                name="StyleChecker",
                instruction="""I am an expert in writing style and formatting standards.
                I check for APA compliance and provide detailed feedback.""",
                server_names=["fetch"],
                context=context,
            ),
            Agent(
                name="Proofreader",
                instruction="""I specialize in grammar, spelling, and clarity.
                I provide detailed corrections and suggestions.""",
                server_names=["filesystem"],
                context=context,
            ),
        ]

        # Create configuration for the Deep Orchestrator
        config = DeepOrchestratorConfig(
            name="DeepAssignmentGrader",
            # available_agents=_predefined_agents,  # UNCOMMENT to use predefined agents
            available_servers=list(context.server_registry.registry.keys()),
            execution=ExecutionConfig(
                max_iterations=25,
                max_replans=2,
                max_task_retries=5,
                enable_parallel=True,
                enable_filesystem=True,
            ),
            budget=BudgetConfig(
                max_tokens=100000,
                max_cost=0.80,
                max_time_minutes=7,
            ),
        )

        # Create the Deep Orchestrator with configuration
        orchestrator = DeepOrchestrator(
            llm_factory=OpenAIAugmentedLLM,
            config=config,
            context=context,
        )

        # Create monitor for state visibility
        monitor = DeepOrchestratorMonitor(orchestrator)

        # Create display layout
        layout = create_display_layout()

        # Define the complex grading task
        task = """
        Analyze the student's short story from short_story.md and create a comprehensive grading report.
        
        The report should include:
        1. Grammar and spelling check with specific corrections
        2. Style analysis against APA guidelines (fetch from https://owl.purdue.edu/owl/research_and_citation/apa_style/apa_formatting_and_style_guide/general_format.html)
        3. Story structure and narrative flow assessment
        4. Factual consistency and logical coherence check
        5. Overall grade with detailed justification
        
        Save the complete grading report to graded_report.md in the same directory.
        
        Use a systematic approach: first understand the story, then analyze each aspect in detail,
        and finally synthesize all findings into a comprehensive report.
        """

        # Store plan reference for display
        orchestrator.current_plan = None

        # Run with live display
        console.print("[yellow]Starting Deep Orchestrator workflow...[/yellow]\n")

        with Live(layout, console=console, refresh_per_second=4) as _live:
            # Update display in background
            async def update_loop():
                while True:
                    try:
                        update_display(layout, monitor)
                        await asyncio.sleep(0.25)  # Reduced from 0.5s
                    except Exception as e:
                        logger.error(f"Display update error: {e}")
                        break

            # Start update loop
            update_task = asyncio.create_task(update_loop())

            try:
                # Run the orchestrator
                start_time = time.time()

                result = await orchestrator.generate_str(
                    message=task,
                    request_params=RequestParams(
                        model="gpt-4o", temperature=0.7, max_iterations=10
                    ),
                )

                result_formatted = (
                    result[:2000] + "..." if len(result) > 2000 else result
                )

                pretty_printer_agent = Agent(
                    name="PrettyPrinter",
                    instruction="Format the output nicely. Extract markdown content and render it in a readable format",
                    context=context,
                )

                async with pretty_printer_agent:
                    pretty_printer = await pretty_printer_agent.attach_llm(
                        OpenAIAugmentedLLM
                    )

                    result_formatted = await pretty_printer.generate_str(
                        message=result,
                        request_params=RequestParams(
                            model="gpt-4o", temperature=0.7, max_iterations=10
                        ),
                    )

                execution_time = time.time() - start_time

                # Final update
                update_display(layout, monitor)

            finally:
                update_task.cancel()
                try:
                    await update_task
                except asyncio.CancelledError:
                    pass

        # Minimal spacing after live display ends
        console.print("[bold green]✨ Grading Complete![/bold green]")

        # Show the grading report
        console.print(
            Panel(
                result_formatted,
                title="📝 Grading Report (Preview)",
                border_style="green",
            )
        )

        # Display final statistics
        console.print("\n[bold cyan]📊 Final Statistics[/bold cyan]")

        # Create summary table
        summary_table = Table(title="Execution Summary", box=box.DOUBLE_EDGE)
        summary_table.add_column("Metric", style="cyan", width=20)
        summary_table.add_column("Value", style="green")

        summary_table.add_row("Total Time", f"{execution_time:.2f}s")
        summary_table.add_row("Iterations", str(orchestrator.iteration))
        summary_table.add_row("Replans", str(orchestrator.replan_count))
        summary_table.add_row(
            "Tasks Completed", str(len(orchestrator.queue.completed_task_names))
        )
        summary_table.add_row(
            "Tasks Failed", str(len(orchestrator.queue.failed_task_names))
        )
        summary_table.add_row(
            "Knowledge Items", str(len(orchestrator.memory.knowledge))
        )
        summary_table.add_row(
            "Artifacts Created", str(len(orchestrator.memory.artifacts))
        )
        summary_table.add_row("Agents Cached", str(len(orchestrator.agent_cache.cache)))
        summary_table.add_row(
            "Cache Hit Rate",
            f"{orchestrator.agent_cache.hits / max(1, orchestrator.agent_cache.hits + orchestrator.agent_cache.misses):.1%}",
        )

        console.print(summary_table)

        # Display budget summary
        budget_summary = orchestrator.budget.get_status_summary()
        console.print(f"\n[yellow]{budget_summary}[/yellow]")

        # Display knowledge learned
        if orchestrator.memory.knowledge:
            console.print("\n[bold cyan]🧠 Knowledge Extracted[/bold cyan]")

            knowledge_table = Table(box=box.SIMPLE)
            knowledge_table.add_column("Category", style="cyan")
            knowledge_table.add_column("Key", style="yellow")
            knowledge_table.add_column("Value", style="green", max_width=50)
            knowledge_table.add_column("Confidence", style="magenta")

            for item in orchestrator.memory.knowledge[:10]:  # Show first 10
                knowledge_table.add_row(
                    item.category,
                    item.key[:30] + "..." if len(item.key) > 30 else item.key,
                    str(item.value)[:50] + "..."
                    if len(str(item.value)) > 50
                    else str(item.value),
                    f"{item.confidence:.2f}",
                )

            console.print(knowledge_table)

        # Display token usage if available
        if context.token_counter:
            summary = await context.token_counter.get_summary()
            console.print(
                f"\n[bold]Total Tokens:[/bold] {summary.usage.total_tokens:,}"
            )
            console.print(f"[bold]Total Cost:[/bold] ${summary.cost:.4f}")

        # Show workspace artifacts if any were created
        if orchestrator.memory.artifacts:
            console.print("\n[bold cyan]📁 Artifacts Created[/bold cyan]")
            for name in list(orchestrator.memory.artifacts.keys())[:5]:
                console.print(f"  • {name}")


if __name__ == "__main__":
    # Change to example directory
    os.chdir(os.path.dirname(os.path.abspath(__file__)))

    # Run the example
    asyncio.run(main())
