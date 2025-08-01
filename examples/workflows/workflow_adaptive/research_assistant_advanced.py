"""
Advanced Research Assistant using Adaptive Workflow V2

A sophisticated example demonstrating all key features of AdaptiveWorkflow:
- Token counting and cost tracking
- Queue visualization and task management
- Knowledge extraction and memory management
- Detailed progress monitoring with Rich
- Comprehensive final report generation

Usage:
    python research_assistant_advanced.py
    python research_assistant_advanced.py --topic "quantum computing applications"
    python research_assistant_advanced.py --max-cost 5.0 --time-limit 10
"""

import asyncio
import argparse
import logging
import os
import time
from datetime import datetime, timedelta, timezone
from typing import List, Dict
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
from rich.table import Table
from rich.live import Live
from rich.layout import Layout
from rich.text import Text

# Configure logging to suppress noise
logging.getLogger().handlers = []
logging.getLogger().addHandler(logging.NullHandler())
logging.getLogger("mcp_agent").setLevel(logging.WARNING)
logging.getLogger("opentelemetry").setLevel(logging.WARNING)

console = Console()


class AdaptiveWorkflowMonitor:
    """Advanced monitor for tracking workflow execution"""

    def __init__(self, workflow: AdaptiveWorkflow):
        self.workflow = workflow
        self.start_time = time.time()
        self.events: deque = deque(maxlen=20)
        self.current_agents: Dict[str, str] = {}
        self.knowledge_items_count = 0
        self.last_update = time.time()

    def add_event(self, icon: str, message: str, detail: str = "", style: str = ""):
        """Add an event to the monitor"""
        timestamp = datetime.now(timezone.utc).strftime("%H:%M:%S")
        self.events.append(
            {
                "time": timestamp,
                "icon": icon,
                "message": message,
                "detail": detail,
                "style": style,
            }
        )

    def get_status_panel(self) -> Panel:
        """Get current status as a Rich panel"""
        if not self.workflow._current_memory:
            return Panel("Initializing...", title="Status", border_style="blue")

        memory = self.workflow._current_memory

        # Create status table
        table = Table(show_header=False, padding=0, box=None)
        table.add_column("Label", style="cyan")
        table.add_column("Value", style="white")

        elapsed = time.time() - self.start_time
        table.add_row("Elapsed", f"{elapsed:.1f}s")
        table.add_row("Iterations", str(memory.iterations))
        table.add_row("Cost", f"${memory.total_cost:.4f}")

        # Token usage
        if self.workflow.context and self.workflow.context.token_counter:
            usage = self.workflow.context.token_counter.get_workflow_usage(
                self.workflow.name
            )
            if usage:
                table.add_row("Tokens", f"{usage.total_tokens:,}")

        # Budget usage
        if hasattr(self.workflow, "budget_manager") and self.workflow.budget_manager:
            budgets = self.workflow.budget_manager.get_budget_status()
            if budgets["cost"]["limit"] < float("inf"):
                cost_pct = (budgets["cost"]["used"] / budgets["cost"]["limit"]) * 100
                table.add_row("Budget", f"{cost_pct:.1f}%")

        return Panel(table, title="📊 Metrics", border_style="blue")

    def get_queue_panel(self) -> Panel:
        """Get task queue visualization"""
        if (
            not hasattr(self.workflow, "subtask_queue")
            or not self.workflow.subtask_queue
        ):
            return Panel("No queue data", title="Task Queue", border_style="yellow")

        queue = self.workflow.subtask_queue
        status = queue.get_queue_status()

        # Create queue visualization
        content = []

        # Summary stats
        stats = Text()
        stats.append(f"Pending: {status['queue_length']} | ", style="yellow")
        stats.append(f"Completed: {status['completed_count']} | ", style="green")
        stats.append(f"Failed: {status['failed_count']}", style="red")
        content.append(stats)
        content.append("")

        # Next tasks
        if status["next_subtasks"]:
            content.append(Text("Next Tasks:", style="bold"))
            for i, task in enumerate(status["next_subtasks"][:5], 1):
                task_text = Text()
                task_text.append(f"{i}. ", style="dim")
                task_text.append(task["name"], style="cyan")
                task_text.append(f" (depth: {task['depth']})", style="dim")
                content.append(task_text)

        return Panel(
            "\n".join(str(c) for c in content),
            title="📋 Task Queue",
            border_style="yellow",
        )

    def get_knowledge_panel(self) -> Panel:
        """Get knowledge/memory visualization"""
        if not self.workflow._current_memory:
            return Panel("No memory data", title="Knowledge Base", border_style="green")

        memory = self.workflow._current_memory

        content = []

        # Knowledge items
        if hasattr(memory, "knowledge_items"):
            items_count = len(memory.knowledge_items)
            content.append(Text(f"Knowledge Items: {items_count}", style="bold"))

            # Show recent high-confidence items
            if memory.knowledge_items:
                recent_items = sorted(
                    memory.knowledge_items[-5:],
                    key=lambda x: x.confidence,
                    reverse=True,
                )[:3]

                content.append("")
                for item in recent_items:
                    item_text = Text()
                    item_text.append("• ", style="green")
                    item_text.append(item.question[:50] + "...", style="cyan")
                    item_text.append(f" ({item.confidence:.2f})", style="dim")
                    content.append(item_text)

        # Failed attempts
        if hasattr(memory, "failed_attempts") and memory.failed_attempts:
            content.append("")
            content.append(
                Text(f"Failed Attempts: {len(memory.failed_attempts)}", style="red")
            )

        return Panel(
            "\n".join(str(c) for c in content),
            title="🧠 Knowledge & Memory",
            border_style="green",
        )

    def get_events_panel(self) -> Panel:
        """Get recent events panel"""
        if not self.events:
            return Panel("No events yet", title="Activity Log", border_style="magenta")

        content = []
        for event in list(self.events)[-10:]:  # Last 10 events
            event_text = Text()
            event_text.append(f"[{event['time']}] ", style="dim")
            event_text.append(event["icon"] + " ")
            event_text.append(event["message"], style=event["style"] or "white")
            if event["detail"]:
                event_text.append(f": {event['detail']}", style="dim")
            content.append(event_text)

        return Panel(
            "\n".join(str(c) for c in content),
            title="📜 Activity Log",
            border_style="magenta",
        )

    def create_dashboard(self) -> Layout:
        """Create full dashboard layout"""
        layout = Layout()

        # Create main sections
        layout.split_column(
            Layout(name="header", size=3),
            Layout(name="body"),
            Layout(name="footer", size=1),
        )

        # Header
        layout["header"].update(
            Panel(
                Text(
                    "🔬 Advanced Research Assistant",
                    style="bold cyan",
                    justify="center",
                ),
                border_style="cyan",
            )
        )

        # Body - split into columns
        layout["body"].split_row(
            Layout(name="left", ratio=1), Layout(name="right", ratio=2)
        )

        # Left column - metrics and queue
        layout["left"].split_column(
            Layout(self.get_status_panel(), name="status"),
            Layout(self.get_queue_panel(), name="queue"),
        )

        # Right column - knowledge and events
        layout["right"].split_column(
            Layout(self.get_knowledge_panel(), name="knowledge", ratio=1),
            Layout(self.get_events_panel(), name="events", ratio=2),
        )

        # Footer
        layout["footer"].update(
            Text("Press Ctrl+C to stop", style="dim", justify="center")
        )

        return layout


async def create_research_agents(context) -> List[Agent]:
    """Create specialized research agents"""

    agents = []

    # Web researcher with access to fetch
    web_researcher = Agent(
        name="WebResearcher",
        instruction="""I specialize in web research. I can:
        - Search and fetch web content
        - Extract key information from websites
        - Verify facts using online sources
        - Find academic papers and documentation""",
        server_names=["fetch"],
        context=context,
    )
    agents.append(web_researcher)

    # File analyst with filesystem access
    file_analyst = Agent(
        name="FileAnalyst",
        instruction="""I analyze and manage local files. I can:
        - Read and analyze documents
        - Create structured reports
        - Organize research findings
        - Save results to appropriate locations""",
        server_names=["filesystem"],
        context=context,
    )
    agents.append(file_analyst)

    # Synthesis expert
    synthesizer = Agent(
        name="SynthesisExpert",
        instruction="""I synthesize information from multiple sources. I can:
        - Combine findings into coherent narratives  
        - Identify patterns and connections
        - Create executive summaries
        - Generate comprehensive reports""",
        server_names=["filesystem", "fetch"],
        context=context,
    )
    agents.append(synthesizer)

    return agents


def display_token_tree(node: TokenNode, prefix: str = "", is_last: bool = True) -> str:
    """Convert token tree to string representation"""
    lines = []

    # Current node
    connector = "└── " if is_last else "├── "
    usage = node.aggregate_usage()

    node_text = f"{prefix}{connector}{node.name}"
    if usage.total_tokens > 0:
        node_text += f" ({usage.total_tokens:,} tokens)"
    lines.append(node_text)

    # Children
    child_prefix = prefix + ("    " if is_last else "│   ")
    children = list(node.children.values())

    for i, child in enumerate(children):
        is_last_child = i == len(children) - 1
        lines.extend(display_token_tree(child, child_prefix, is_last_child).split("\n"))

    return "\n".join(lines)


def generate_final_report(
    workflow: AdaptiveWorkflow, monitor: AdaptiveWorkflowMonitor, elapsed: float
) -> str:
    """Generate comprehensive final report"""

    lines = ["# Research Assistant - Final Report", ""]

    # Executive Summary
    lines.extend(
        [
            "## Executive Summary",
            f"- **Total Time**: {elapsed:.1f} seconds",
            f"- **Iterations**: {workflow._current_memory.iterations if workflow._current_memory else 0}",
            f"- **Total Cost**: ${workflow._current_memory.total_cost:.4f}"
            if workflow._current_memory
            else "- **Total Cost**: $0.00",
            "",
        ]
    )

    # Task Execution Summary
    if hasattr(workflow, "subtask_queue") and workflow.subtask_queue:
        status = workflow.subtask_queue.get_queue_status()
        lines.extend(
            [
                "## Task Execution Summary",
                f"- **Tasks Completed**: {status['completed_count']}",
                f"- **Tasks Failed**: {status['failed_count']}",
                f"- **Tasks Remaining**: {status['queue_length']}",
                "",
            ]
        )

    # Knowledge Extracted
    if workflow._current_memory and hasattr(
        workflow._current_memory, "knowledge_items"
    ):
        lines.extend(
            [
                "## Knowledge Extracted",
                f"Total knowledge items: {len(workflow._current_memory.knowledge_items)}",
                "",
            ]
        )

        # Top findings by confidence
        if workflow._current_memory.knowledge_items:
            top_items = sorted(
                workflow._current_memory.knowledge_items,
                key=lambda x: x.confidence,
                reverse=True,
            )[:5]

            lines.append("### Top Findings (by confidence):")
            for i, item in enumerate(top_items, 1):
                lines.append(f"{i}. **{item.question}**")
                lines.append(f"   - Answer: {item.answer[:200]}...")
                lines.append(f"   - Confidence: {item.confidence:.2f}")
                lines.append("")

    # Token Usage Breakdown
    if workflow.context and workflow.context.token_counter:
        lines.extend(["## Token Usage Analysis", ""])

        summary = workflow.context.token_counter.get_summary()
        lines.extend(
            [
                f"- **Total Tokens**: {summary.usage.total_tokens:,}",
                f"- **Input Tokens**: {summary.usage.input_tokens:,}",
                f"- **Output Tokens**: {summary.usage.output_tokens:,}",
                f"- **Total Cost**: ${summary.cost:.4f}",
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

    # Error Summary
    if workflow._current_memory and hasattr(
        workflow._current_memory, "failed_attempts"
    ):
        if workflow._current_memory.failed_attempts:
            lines.extend(
                [
                    "## Error Summary",
                    f"Total errors encountered: {len(workflow._current_memory.failed_attempts)}",
                    "",
                ]
            )

            # Show last few errors
            for attempt in workflow._current_memory.failed_attempts[-3:]:
                lines.append(
                    f"- {attempt['action']} at iteration {attempt['iteration']}: {attempt['error']}"
                )
            lines.append("")

    # Research History
    if workflow._current_memory and hasattr(
        workflow._current_memory, "research_history"
    ):
        lines.extend(
            [
                "## Research Progress",
                f"Total research phases: {len(workflow._current_memory.research_history)}",
                "",
            ]
        )

    return "\n".join(lines)


app = MCPApp(name="research_assistant_advanced")


async def main(topic: str = None, max_cost: float = 3.0, time_limit: int = 5):
    """Run the advanced research assistant"""

    async with app.run() as research_app:
        console.clear()

        # Default topic if not provided
        if not topic:
            topic = """Research the latest developments in AI safety and alignment. 
            Focus on recent breakthroughs, key researchers, major challenges, 
            and practical applications. Provide a comprehensive overview suitable 
            for both technical and non-technical audiences."""

        # Configure servers
        research_app.context.config.mcp.servers["filesystem"].args.extend([os.getcwd()])

        # Create agents
        with console.status("[cyan]Creating research agents..."):
            agents = await create_research_agents(research_app.context)

        # Create memory manager
        memory_manager = MemoryManager(enable_learning=True, max_memories=100)

        # LLM factory
        def llm_factory(agent: Agent) -> OpenAIAugmentedLLM:
            return OpenAIAugmentedLLM(
                agent=agent,
                context=research_app.context,
            )

        # Create workflow
        workflow = AdaptiveWorkflow(
            llm_factory=llm_factory,
            name="ResearchAssistant",
            available_agents=agents,
            available_servers=["filesystem", "fetch"],
            task_type=TaskType.RESEARCH,
            time_budget=timedelta(minutes=time_limit),
            cost_budget=max_cost,
            max_iterations=15,
            enable_parallel=True,
            memory_manager=memory_manager,
            context=research_app.context,
            model_preferences=ModelPreferences(
                model="gpt-4o",
                costPriority=0.3,
                speedPriority=0.2,
                intelligencePriority=0.5,
            ),
        )

        # Create monitor
        monitor = AdaptiveWorkflowMonitor(workflow)
        monitor.add_event("🚀", "Research Assistant Started", style="bold cyan")

        # Patch workflow methods to track events
        original_analyze = workflow._analyze_objective

        async def patched_analyze(*args, **kwargs):
            monitor.add_event("📊", "Analyzing objective", style="yellow")
            result = await original_analyze(*args, **kwargs)
            monitor.add_event("✅", "Objective analyzed", style="green")
            return result

        workflow._analyze_objective = patched_analyze

        original_plan = workflow._plan_research

        async def patched_plan(*args, **kwargs):
            monitor.add_event("📝", "Planning research", style="yellow")
            result = await original_plan(*args, **kwargs)
            if result:
                monitor.add_event(
                    "✅", "Research planned", f"{len(result)} aspects", "green"
                )
            return result

        workflow._plan_research = patched_plan

        original_execute = workflow._execute_single_subtask

        async def patched_execute(subtask, *args, **kwargs):
            agent_name = (
                subtask.aspect.name if hasattr(subtask, "aspect") else "Unknown"
            )
            monitor.add_event("🤖", f"Executing: {agent_name}", style="cyan")
            result = await original_execute(subtask, *args, **kwargs)
            monitor.add_event("✅", f"Completed: {agent_name}", style="green")
            return result

        workflow._execute_single_subtask = patched_execute

        # Run with live dashboard
        with Live(
            monitor.create_dashboard(), refresh_per_second=2, console=console
        ) as live:
            start_time = time.time()

            # Update dashboard in background
            async def update_dashboard():
                while True:
                    try:
                        live.update(monitor.create_dashboard())
                        await asyncio.sleep(0.5)
                    except Exception:
                        break

            dashboard_task = asyncio.create_task(update_dashboard())

            try:
                # Execute research
                result = await workflow.generate_str(
                    message=topic,
                    request_params=RequestParams(
                        model="gpt-4o", temperature=0.7, max_iterations=15
                    ),
                )

                elapsed = time.time() - start_time
                monitor.add_event(
                    "✅", "Research completed!", f"Time: {elapsed:.1f}s", "bold green"
                )

            finally:
                dashboard_task.cancel()

        # Display results
        console.clear()
        console.print("\n[bold cyan]🔬 Research Assistant - Results[/bold cyan]")
        console.print("=" * 80 + "\n")

        # Show research output
        if result:
            console.print(
                Panel(
                    result[:1000] + "..." if len(result) > 1000 else result,
                    title="Research Output",
                    border_style="green",
                )
            )

        # Token usage tree
        if workflow.context and workflow.context.token_counter:
            root_node = workflow.context.token_counter.get_node(workflow.name)
            if root_node:
                console.print("\n[bold]Token Usage Tree:[/bold]")
                console.print(display_token_tree(root_node))

        # Generate and display final report
        final_report = generate_final_report(workflow, monitor, elapsed)
        console.print(
            "\n" + Panel(final_report, title="Final Report", border_style="blue")
        )

        # Save outputs
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")

        # Save research results
        with open(f"research_output_{timestamp}.md", "w") as f:
            f.write(f"# Research Output\n\nTopic: {topic}\n\n{result}")

        # Save detailed report
        with open(f"research_report_{timestamp}.md", "w") as f:
            f.write(final_report)

        console.print(
            f"\n[green]✅ Results saved to research_output_{timestamp}.md[/green]"
        )
        console.print(
            f"[green]✅ Report saved to research_report_{timestamp}.md[/green]\n"
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Advanced Research Assistant using Adaptive Workflow"
    )
    parser.add_argument("--topic", type=str, help="Research topic (default: AI safety)")
    parser.add_argument(
        "--max-cost", type=float, default=3.0, help="Maximum cost budget in dollars"
    )
    parser.add_argument(
        "--time-limit", type=int, default=5, help="Time limit in minutes"
    )

    args = parser.parse_args()

    # Change to example directory
    os.chdir(os.path.dirname(os.path.abspath(__file__)))

    asyncio.run(
        main(topic=args.topic, max_cost=args.max_cost, time_limit=args.time_limit)
    )
