"""
Adaptive Workflow V2 Example

This example demonstrates the Adaptive Workflow V2, which implements
the Deep Research architecture with cleaner separation of concerns,
predefined agent support, and provider-agnostic message handling.

Key differences from V1:
- Simplified memory management without rigid categorization
- Support for predefined agents (reuse existing specialized agents)
- Native message format handling (provider-agnostic)
- Non-cascading iteration limits per subagent
- Cleaner phase separation (analyze, plan, execute, synthesize, decide)
"""

import asyncio
import os
from datetime import timedelta
from typing import List
from pydantic import BaseModel, Field

from mcp_agent.app import MCPApp
from mcp_agent.agents.agent import Agent
from mcp_agent.workflows.llm.augmented_llm import RequestParams
from mcp_agent.workflows.llm.augmented_llm_openai import OpenAIAugmentedLLM
from mcp_agent.workflows.adaptive.adaptive_workflow import AdaptiveWorkflow
from mcp_agent.workflows.adaptive.models import ExecutionResult
from mcp_agent.workflows.adaptive.memory import MemoryManager, FileSystemBackend
from mcp.types import ModelPreferences
from rich import print
from rich.console import Console
from rich.table import Table

console = Console()


class ProjectAnalysis(BaseModel):
    """Structured output for project analysis"""

    architecture_patterns: List[str] = Field(
        description="Key architectural patterns found"
    )
    tech_stack: List[str] = Field(description="Technologies and frameworks used")
    complexity_score: float = Field(
        ge=0.0, le=10.0, description="Overall complexity (0-10)"
    )
    recommendations: List[str] = Field(description="Improvement recommendations")
    security_concerns: List[str] = Field(description="Potential security issues")


async def create_specialized_agents(context) -> List[Agent]:
    """Create specialized agents that can be reused by the workflow"""

    # Code Analysis Agent - specializes in reading and analyzing code
    code_agent = Agent(
        name="CodeAnalyzer",
        instruction="""I am a specialized code analysis agent. I excel at:
        - Reading and understanding code structure
        - Identifying design patterns and anti-patterns
        - Evaluating code quality and complexity
        - Finding potential bugs and security issues
        I use filesystem tools to navigate and analyze codebases.""",
        server_names=["filesystem"],
        context=context,
    )

    # Documentation Agent - specializes in reading and creating documentation
    docs_agent = Agent(
        name="DocumentationExpert",
        instruction="""I am a documentation specialist. I excel at:
        - Reading and understanding technical documentation
        - Creating clear, structured documentation
        - Generating API documentation
        - Writing user guides and tutorials
        I work with filesystem tools to manage documentation.""",
        server_names=["filesystem"],
        context=context,
    )

    # Web Research Agent - specializes in web searches and research
    web_agent = Agent(
        name="WebResearcher",
        instruction="""I am a web research specialist. I excel at:
        - Finding relevant information online
        - Comparing technologies and solutions
        - Researching best practices and standards
        - Gathering community insights and trends
        I use web search tools to gather information.""",
        server_names=["websearch"],  # Assuming websearch server is configured
        context=context,
    )

    return [code_agent, docs_agent, web_agent]


async def display_execution_summary(result: ExecutionResult):
    """Display a rich summary of the execution"""
    table = Table(title="Execution Summary", show_header=True)
    table.add_column("Metric", style="cyan", width=20)
    table.add_column("Value", style="green")

    table.add_row("Execution ID", result.execution_id[:8] + "...")
    table.add_row("Task Type", result.task_type)
    table.add_row("Success", "✓" if result.success else "✗")
    table.add_row("Confidence", f"{result.confidence:.2%}")
    table.add_row("Iterations", str(result.iterations))
    table.add_row("Subagents Used", str(result.subagents_used))
    table.add_row("Total Time", f"{result.total_time_seconds:.2f}s")
    table.add_row("Total Cost", f"${result.total_cost:.4f}")

    console.print(table)


async def main():
    """Run adaptive workflow V2 examples"""
    async with MCPApp("config/mcp_agent.config.yaml") as app:
        # Create specialized agents
        specialized_agents = await create_specialized_agents(app.context)

        # Set up persistent memory
        memory_backend = FileSystemBackend("./workflow_memory")
        memory_manager = MemoryManager(backend=memory_backend, enable_learning=True)

        # Define the LLM factory
        def llm_factory(agent: Agent) -> OpenAIAugmentedLLM:
            return OpenAIAugmentedLLM(
                agent=agent,
                context=app.context,
            )

        # Create the adaptive workflow V2 with predefined agents
        workflow = AdaptiveWorkflow(
            llm_factory=llm_factory,
            name="AdaptiveResearchWorkflowV2",
            available_agents=specialized_agents,  # Provide specialized agents
            available_servers=list(app.context.servers.keys()),
            time_budget=timedelta(minutes=5),
            cost_budget=3.0,
            max_iterations=8,  # Fewer iterations, more focused
            enable_parallel=True,
            memory_manager=memory_manager,  # Enable persistent memory
            context=app.context,
        )

        # Example 1: Deep Code Analysis with Predefined Agents
        print(
            "\n[bold cyan]Example 1: Deep Code Analysis with Predefined Agents[/bold cyan]"
        )
        print("Analyzing the adaptive workflow implementation itself...\n")

        code_analysis = await workflow.generate(
            message="""Analyze the AdaptiveWorkflowV2 implementation in this codebase. 
            Focus on:
            1. Overall architecture and design patterns
            2. How it implements the Deep Research pattern
            3. Integration with predefined agents
            4. Potential improvements or issues
            
            Use the CodeAnalyzer agent to examine the code structure."""
        )

        # The result is in native message format
        print("[green]Analysis Complete:[/green]")
        # Extract and display the actual content
        for msg in code_analysis:
            if hasattr(msg, "content"):
                console.print(msg.content)
            else:
                console.print(str(msg))

        # Example 2: Multi-Agent Research Task
        print("\n[bold cyan]Example 2: Multi-Agent Research Task[/bold cyan]")
        print("Researching modern agent architectures using multiple specialists...\n")

        research_result = await workflow.generate_str(
            message="""Research modern multi-agent architectures and frameworks. 
            I want to understand:
            1. Current state-of-the-art approaches (use WebResearcher)
            2. Implementation patterns in popular frameworks (use CodeAnalyzer)
            3. Best practices documentation (use DocumentationExpert)
            
            Synthesize findings into a comprehensive overview."""
        )

        print(f"[green]Research Result:[/green]\n{research_result}\n")

        # Example 3: Structured Project Analysis
        print("\n[bold cyan]Example 3: Structured Project Analysis[/bold cyan]")
        print("Getting structured analysis of the project...\n")

        structured_analysis = await workflow.generate_structured(
            message="""Analyze this MCP Agent project comprehensively:
            - Examine the codebase architecture
            - Identify key design patterns
            - Assess complexity and maintainability
            - Suggest improvements
            - Note any security concerns
            
            Use all available specialized agents as needed.""",
            response_model=ProjectAnalysis,
        )

        print("[green]Structured Analysis:[/green]")
        console.print(structured_analysis.model_dump_json(indent=2))

        # Example 4: Learning from Past Executions
        print("\n[bold cyan]Example 4: Adaptive Learning Demonstration[/bold cyan]")
        print("Testing memory and learning capabilities...\n")

        # First execution - workflow learns
        _ = await workflow.generate_str(
            message="What are the key components of the MCP protocol implementation in this codebase?"
        )

        print(
            "[yellow]First execution complete. Workflow has learned from this...[/yellow]\n"
        )

        # Second similar execution - should be faster/more efficient
        second_result = await workflow.generate_str(
            message="Explain the MCP server implementation patterns in this codebase"
        )

        print(f"[green]Adaptive Result:[/green]\n{second_result[:500]}...\n")

        # Example 5: Speed-Optimized Query with Constraints
        print("\n[bold cyan]Example 5: Speed-Optimized Query[/bold cyan]")
        print("Quick analysis with strict constraints...\n")

        fast_params = RequestParams(
            modelPreferences=ModelPreferences(
                speedPriority=0.9,
                intelligencePriority=0.1,
                costPriority=0.0,
            ),
            max_iterations=2,  # Very limited iterations
            temperature=0.3,  # More focused responses
        )

        fast_result = await workflow.generate_str(
            message="List the main Python files in the adaptive workflow implementation",
            request_params=fast_params,
        )

        print(f"[green]Fast Result:[/green]\n{fast_result}\n")

        # Example 6: Complex Hybrid Task
        print("\n[bold cyan]Example 6: Complex Hybrid Task[/bold cyan]")
        print("Research, analyze, and create documentation...\n")

        hybrid_result = await workflow.generate_str(
            message="""Complete the following multi-phase task:
            1. Research best practices for Python async/await patterns
            2. Analyze how async is used in the AdaptiveWorkflowV2 implementation
            3. Create a brief guide for improving async patterns in the codebase
            
            Use appropriate specialized agents for each phase."""
        )

        print(f"[green]Hybrid Task Result:[/green]\n{hybrid_result[:1000]}...\n")

        # Display execution history
        print("\n[bold cyan]Execution History Summary[/bold cyan]")
        executions = await memory_manager.list_executions()

        history_table = Table(title="Recent Executions", show_header=True)
        history_table.add_column("Time", style="cyan")
        history_table.add_column("Objective", style="yellow", width=40)
        history_table.add_column("Type", style="green")
        history_table.add_column("Cost", style="red")

        for exec_id, exec_data in list(executions.items())[-5:]:  # Last 5
            if "memory" in exec_data:
                mem = exec_data["memory"]
                history_table.add_row(
                    exec_data.get("timestamp", "Unknown"),
                    mem.get("objective", "N/A")[:40] + "...",
                    mem.get("task_type", "N/A"),
                    f"${mem.get('total_cost', 0):.3f}",
                )

        console.print(history_table)

        # Example 7: Demonstrate Error Handling
        print("\n[bold cyan]Example 7: Error Handling and Recovery[/bold cyan]")
        print("Testing workflow resilience...\n")

        error_result = await workflow.generate_str(
            message="""Try to analyze a non-existent file: /tmp/does_not_exist/phantom.py
            Then recover and provide insights about error handling in the workflow."""
        )

        print(f"[green]Error Handling Result:[/green]\n{error_result}\n")


if __name__ == "__main__":
    # Change to the example directory
    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    asyncio.run(main())
