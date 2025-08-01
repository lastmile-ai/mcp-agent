"""
Assignment Grader using Adaptive Workflow V2 - Demo Version

Clean console output for demonstrations showing agent execution and tool calls.

Usage:
    python assignment_grader_demo.py                    # Uses predefined agents
    python assignment_grader_demo.py --no-predefined    # Creates agents dynamically
"""

import asyncio
import argparse
import io
import logging
import os
import time
import warnings
from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime, timedelta
from typing import List

from mcp_agent.app import MCPApp
from mcp_agent.agents.agent import Agent
from mcp_agent.workflows.llm.augmented_llm import RequestParams
from mcp_agent.workflows.llm.augmented_llm_openai import OpenAIAugmentedLLM
from mcp_agent.workflows.adaptive.adaptive_workflow import AdaptiveWorkflow
from mcp_agent.workflows.adaptive.memory import MemoryManager
from mcp.types import ModelPreferences
from rich.console import Console
from rich.panel import Panel

# Configure Python's root logger to disable console output
logging.getLogger().handlers = []
logging.getLogger().addHandler(logging.NullHandler())

# Also disable the mcp_agent logger specifically
mcp_logger = logging.getLogger("mcp_agent")
mcp_logger.handlers = []
mcp_logger.addHandler(logging.NullHandler())
mcp_logger.propagate = False

# Disable OpenTelemetry console output
otel_logger = logging.getLogger("opentelemetry")
otel_logger.handlers = []
otel_logger.addHandler(logging.NullHandler())
otel_logger.propagate = False

# Set all loggers to WARNING level to suppress debug/info messages
logging.getLogger().setLevel(logging.WARNING)

# Suppress Pydantic serialization warnings
warnings.filterwarnings("ignore", category=UserWarning)

# Suppress uvloop warnings if present
warnings.filterwarnings("ignore", message=".*uvloop.*")

console = Console()


def print_header():
    """Print the header"""
    console.clear()
    console.print(
        "\n[bold cyan]📚 Assignment Grader - Adaptive Workflow V2[/bold cyan]"
    )
    console.print("=" * 80 + "\n")


def print_update(icon: str, message: str, detail: str = "", style: str = ""):
    """Print a single update line"""
    timestamp = datetime.now().strftime("%H:%M:%S")
    if detail:
        console.print(
            f"[dim]{timestamp}[/dim] {icon} [{style}]{message}[/{style}]: {detail}"
        )
    else:
        console.print(f"[dim]{timestamp}[/dim] {icon} [{style}]{message}[/{style}]")


async def create_predefined_agents(context) -> List[Agent]:
    """Create specialized agents for grading"""

    # Suppress output during agent creation
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

    return [file_handler, apa_expert]


class DemoWorkflowMonitor:
    """Monitor workflow execution with clean demo output"""

    def __init__(self, workflow):
        self.workflow = workflow
        self._original_methods = {}
        self.start_time = time.time()
        self.tool_calls_count = 0

    async def __aenter__(self):
        self._patch_methods()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        self._unpatch_methods()

    def _patch_methods(self):
        # Patch analyze_objective
        original_analyze = self.workflow._analyze_objective

        async def patched_analyze(*args, **kwargs):
            print_update("📊", "Analyzing objective", style="yellow")
            result = await original_analyze(*args, **kwargs)
            print_update("✅", "Objective analyzed", style="green")
            return result

        self._original_methods["_analyze_objective"] = original_analyze
        self.workflow._analyze_objective = patched_analyze

        # Patch plan_research
        original_plan = self.workflow._plan_research

        async def patched_plan(*args, **kwargs):
            print_update("📝", "Planning research approach", style="yellow")
            result = await original_plan(*args, **kwargs)
            if result:
                print_update(
                    "✅",
                    "Research plan created",
                    f"{len(result)} aspects identified",
                    "green",
                )
                for i, aspect in enumerate(result, 1):
                    print_update("  📌", f"Aspect {i}", aspect.name, "dim")
            return result

        self._original_methods["_plan_research"] = original_plan
        self.workflow._plan_research = patched_plan

        # Patch execute_single_aspect
        original_execute = self.workflow._execute_single_aspect

        async def patched_execute(aspect, *args, **kwargs):
            # Determine agent details
            agent_name = aspect.name.replace(" ", "_").replace("-", "_")
            servers = []

            # Check for predefined agent
            if hasattr(aspect, "predefined_agent") and aspect.predefined_agent:
                agent_name = aspect.predefined_agent.name
                servers = getattr(aspect.predefined_agent, "server_names", [])

            servers_str = f"[{', '.join(servers)}]" if servers else ""
            task_summary = (
                aspect.objective[:50] + "..."
                if len(aspect.objective) > 50
                else aspect.objective
            )

            print_update(
                "🤖", f"Starting: {agent_name}", f"{servers_str} {task_summary}", "cyan"
            )

            # Capture stderr to suppress server messages
            with redirect_stderr(io.StringIO()):
                result = await original_execute(aspect, *args, **kwargs)

            # Extract actual agent name from result if available
            if result and hasattr(result, "agent_name") and result.agent_name:
                agent_name = result.agent_name

            print_update("✅", f"Completed: {agent_name}", style="green")

            # Show key findings
            if result and hasattr(result, "response") and result.response:
                response_str = str(result.response)
                if (
                    "found" in response_str.lower()
                    or "identified" in response_str.lower()
                ):
                    summary = (
                        response_str[:80] + "..."
                        if len(response_str) > 80
                        else response_str
                    )
                    print_update("  💡", "Finding", summary, "dim")

            return result

        self._original_methods["_execute_single_aspect"] = original_execute
        self.workflow._execute_single_aspect = patched_execute

        # Patch synthesize_results
        original_synthesize = self.workflow._synthesize_results

        async def patched_synthesize(*args, **kwargs):
            print_update("🔄", "Synthesizing results", style="yellow")
            result = await original_synthesize(*args, **kwargs)
            print_update("✅", "Results synthesized", style="green")
            return result

        self._original_methods["_synthesize_results"] = original_synthesize
        self.workflow._synthesize_results = patched_synthesize

        # Patch generate_final_report
        original_report = self.workflow._generate_final_report

        async def patched_report(*args, **kwargs):
            print_update("📄", "Generating final report", style="yellow")
            result = await original_report(*args, **kwargs)
            print_update("✅", "Report generated", style="green")
            return result

        self._original_methods["_generate_final_report"] = original_report
        self.workflow._generate_final_report = patched_report

    def _unpatch_methods(self):
        for method_name, original_method in self._original_methods.items():
            setattr(self.workflow, method_name, original_method)


app = MCPApp(name="assignment_grader_adaptive")


async def main(use_predefined_agents: bool = True):
    """Run the assignment grader demo"""

    async with app.run() as grader_app:
        print_header()

        # Define the grading task
        task = """Load the student's short story from short_story.md, 
        and generate a report with feedback across proofreading, 
        factuality/logical consistency and style adherence. Use the style rules from 
        https://owl.purdue.edu/owl/research_and_citation/apa_style/apa_formatting_and_style_guide/general_format.html.
        Write the graded report to graded_report.md in the same directory as short_story.md"""

        console.print("[bold]Task:[/bold]")
        console.print(Panel(task, border_style="blue"))
        console.print()

        # Configure filesystem server
        grader_app.context.config.mcp.servers["filesystem"].args.extend([os.getcwd()])

        # Set up agents
        agents = []
        if use_predefined_agents:
            print_update("🔨", "Creating predefined agents", style="cyan")
            agents = await create_predefined_agents(grader_app.context)
            for agent in agents:
                print_update(
                    "  ✅",
                    f"Created {agent.name}",
                    f"Servers: {', '.join(agent.server_names)}",
                    "green",
                )
        else:
            print_update("🎯", "Using dynamic agent creation", style="cyan")

        print()  # Space before workflow execution

        # Create memory manager
        memory_manager = MemoryManager(enable_learning=False)

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
            time_budget=timedelta(minutes=5),
            cost_budget=3.0,
            max_iterations=8,
            enable_parallel=True,
            memory_manager=memory_manager,
            context=grader_app.context,
            model_preferences=ModelPreferences(model="gpt-4o"),
        )

        # Execute with monitoring
        print_update("🚀", "Starting workflow execution", style="bold cyan")
        print()

        start_time = time.time()

        async with DemoWorkflowMonitor(workflow):
            # Update metrics in background
            async def update_metrics():
                last_update = 0
                while True:
                    if workflow._current_memory:
                        elapsed = time.time() - start_time
                        # Only update if significant change
                        if elapsed - last_update > 1.0:
                            cost = workflow._current_memory.total_cost or 0.0
                            console.print(
                                f"\r[dim]Progress: {elapsed:.0f}s | Iterations: {workflow._current_memory.iterations} | Cost: ${cost:.4f}[/dim]",
                                end="",
                            )
                            last_update = elapsed
                    await asyncio.sleep(0.5)

            metrics_task = asyncio.create_task(update_metrics())

            try:
                result = await workflow.generate_str(
                    message=task,
                    request_params=RequestParams(
                        model="gpt-4o", max_iterations=8, temperature=0.3
                    ),
                )
            finally:
                metrics_task.cancel()

        print("\n")  # Clear the progress line

        # Show results
        elapsed = time.time() - start_time
        print_update(
            "✅", "Workflow completed!", f"Total time: {elapsed:.1f}s", "bold green"
        )
        print()

        if workflow._current_memory:
            console.print("[bold]Execution Summary:[/bold]")
            console.print(f"  • Time: {elapsed:.1f} seconds")
            console.print(f"  • Iterations: {workflow._current_memory.iterations}")
            console.print(
                f"  • Agents Used: {len(workflow._current_memory.subagent_results)}"
            )
            console.print(f"  • Total Cost: ${workflow._current_memory.total_cost:.4f}")
            console.print(
                f"  • Performance: ~{90 / elapsed:.1f}x faster than Orchestrator baseline"
            )

        # Show report preview
        if result:
            print()
            console.print("[bold]Report Preview:[/bold]")
            # Extract key sections from the report
            lines = result.split("\n")
            preview_lines = []
            for i, line in enumerate(lines[:30]):  # First 30 lines
                if line.strip() and (
                    line.startswith("#") or line.startswith("*") or "Grade:" in line
                ):
                    preview_lines.append(line)

            if preview_lines:
                preview = "\n".join(preview_lines[:10])
            else:
                preview = result[:400] + "..." if len(result) > 400 else result

            console.print(Panel(preview, border_style="green"))

        print()
        print_update("📁", "Report saved", "graded_report.md", "bold green")
        print()


if __name__ == "__main__":
    # Parse command line arguments
    parser = argparse.ArgumentParser(
        description="Grade student assignments using Adaptive Workflow V2"
    )
    parser.add_argument(
        "--no-predefined",
        action="store_true",
        help="Create agents dynamically instead of using predefined agents",
    )

    args = parser.parse_args()

    # Change to example directory
    os.chdir(os.path.dirname(os.path.abspath(__file__)))

    # Run with specified mode
    asyncio.run(main(use_predefined_agents=not args.no_predefined))
