import asyncio
import os

from mcp_agent.app import MCPApp
from mcp_agent.agents.agent import Agent
from mcp_agent.core.context import Context
from mcp_agent.workflows.llm.augmented_llm import RequestParams
from mcp_agent.workflows.llm.augmented_llm_openai import OpenAIAugmentedLLM
from mcp_agent.workflows.orchestrator.orchestrator import Orchestrator
from mcp_agent.tracing.token_counter import TokenNode

from rich import print

# The orchestrator is a high-level abstraction that allows you to generate dynamic plans
# and execute them using multiple agents and servers.
# Here is the example plan generate by a planner for the example below.
# {
#   "data": {
#     "steps": [
#       {
#         "description": "Load the short story from short_story.md.",
#         "tasks": [
#           {
#             "description": "Find and read the contents of short_story.md.",
#             "agent": "finder"
#           }
#         ]
#       },
#       {
#         "description": "Generate feedback on the short story.",
#         "tasks": [
#           {
#             "description": "Review the short story for grammar, spelling, and punctuation errors and provide detailed feedback.",
#             "agent": "proofreader"
#           },
#           {
#             "description": "Check the short story for factual consistency and logical coherence, and highlight any inconsistencies.",
#             "agent": "fact_checker"
#           },
#           {
#             "description": "Evaluate the short story for style adherence according to APA style guidelines and suggest improvements.",
#             "agent": "style_enforcer"
#           }
#         ]
#       },
#       {
#         "description": "Combine the feedback into a comprehensive report.",
#         "tasks": [
#           {
#             "description": "Compile the feedback on proofreading, factuality, and style adherence to create a comprehensive graded report.",
#             "agent": "writer"
#           }
#         ]
#       },
#       {
#         "description": "Write the graded report to graded_report.md.",
#         "tasks": [
#           {
#             "description": "Save the compiled feedback as graded_report.md in the same directory as short_story.md.",
#             "agent": "writer"
#           }
#         ]
#       }
#     ],
#     "is_complete": false
#   }
# }

# It produces a report like graded_report.md, which contains the feedback from the proofreader, fact checker, and style enforcer.
#  The objective to analyze "The Battle of Glimmerwood" and generate a comprehensive feedback report has been successfully accomplished. The process involved several sequential and
# detailed evaluation steps, each contributing to the final assessment:

# 1. **Content Retrieval**: The short story was successfully located and read from `short_story.md`. This enabled subsequent analyses on the complete narrative content.

# 2. **Proofreading**: The text was rigorously reviewed for grammar, spelling, and punctuation errors. Specific corrections were suggested, enhancing both clarity and readability. Suggestions for improving the narrative's clarity were also provided,
# advising more context for characters, stakes clarification, and detailed descriptions to immerse readers.

# 3. **Factual and Logical Consistency**: The story's overall consistency was verified, examining location, plot development, and character actions. Although largely logical within its mystical context, the narrative contained unresolved elements about
# the Glimmerstones' power. Addressing these potential inconsistencies would strengthen its coherence.

# 4. **Style Adherence**: Evaluated against APA guidelines, the story was reviewed for format compliance, grammatical correctness, clarity, and tone. Although the narrative inherently diverges due to its format, suggestions for more formal alignment in
# future academic contexts were provided.

# 5. **Report Compilation**: All findings, corrections, and enhancement suggestions were compiled into the graded report, `graded_report.md`, situated in the same directory as the original short story.

# The completed graded report encapsulates detailed feedback across all targeted areas, providing a comprehensive evaluation for the student's work. It highlights essential improvements and ensures adherence to APA style rules, where applicable,
# fulfilling the complete objective satisfactorily.
# Total run time: 89.78s

app = MCPApp(name="assignment_grader_orchestrator")


@app.tool
async def example_usage() -> str:
    """
    this example function/tool call will use an orchestrator workflow
    to dynamically plan and execute across a number of agents to grade
    a short story.
    """
    result = ""
    async with app.run() as orchestrator_app:
        logger = orchestrator_app.logger

        context = orchestrator_app.context
        logger.info("Current config:", data=context.config.model_dump())

        # Add the current directory to the filesystem server's args
        context.config.mcp.servers["filesystem"].args.extend([os.getcwd()])

        finder_agent = Agent(
            name="finder",
            instruction="""You are an agent with access to the filesystem, 
            as well as the ability to fetch URLs. Your job is to identify 
            the closest match to a user's request, make the appropriate tool calls, 
            and return the URI and CONTENTS of the closest match.""",
            server_names=["fetch", "filesystem"],
        )

        writer_agent = Agent(
            name="writer",
            instruction="""You are an agent that can write to the filesystem.
            You are tasked with taking the user's input, addressing it, and 
            writing the result to disk in the appropriate location.""",
            server_names=["filesystem"],
        )

        proofreader = Agent(
            name="proofreader",
            instruction=""""Review the short story for grammar, spelling, and punctuation errors.
            Identify any awkward phrasing or structural issues that could improve clarity. 
            Provide detailed feedback on corrections.""",
            server_names=["fetch"],
        )

        fact_checker = Agent(
            name="fact_checker",
            instruction="""Verify the factual consistency within the story. Identify any contradictions,
            logical inconsistencies, or inaccuracies in the plot, character actions, or setting. 
            Highlight potential issues with reasoning or coherence.""",
            server_names=["fetch"],
        )

        style_enforcer = Agent(
            name="style_enforcer",
            instruction="""Analyze the story for adherence to style guidelines.
            Evaluate the narrative flow, clarity of expression, and tone. Suggest improvements to 
            enhance storytelling, readability, and engagement.""",
            server_names=["fetch"],
        )

        # We give the orchestrator a very varied task, which
        # requires the use of multiple agents and MCP servers.
        task = """Load the student's short story from short_story.md, 
        and generate a report with feedback across proofreading, 
        factuality/logical consistency and style adherence. Use the style rules from 
        https://owl.purdue.edu/owl/research_and_citation/apa_style/apa_formatting_and_style_guide/general_format.html.
        Write the graded report to graded_report.md in the same directory as short_story.md"""

        orchestrator = Orchestrator(
            llm_factory=OpenAIAugmentedLLM,
            available_agents=[
                finder_agent,
                writer_agent,
                proofreader,
                fact_checker,
                style_enforcer,
            ],
            # We will let the orchestrator iteratively plan the task at every step
            plan_type="full",
            name="assignment_grader",
        )

        result = await orchestrator.generate_str(
            message=task, request_params=RequestParams(model="gpt-4o")
        )
        logger.info(f"{result}")

        # Display token usage tree for the orchestrator workflow using helper
        node = await orchestrator.get_token_node()
        if node:
            display_node_tree(node, context=context)

        # Show summary at the bottom (use convenience API)
        summary = await orchestrator_app.get_token_summary()
        print(f"\nTotal Cost: ${summary.cost:.4f}")
        print("=" * 60)
    return result


def display_node_tree(
    node: TokenNode,
    indent: str = "",
    is_last: bool = True,
    context: Context | None = None,
    skip_empty: bool = True,
):
    """Display a node and its children with aggregate token usage and cost."""
    # Connector symbols
    connector = "└── " if is_last else "├── "

    # Get aggregate usage and cost via node helpers
    usage = node.get_usage()
    cost = node.get_cost() if hasattr(node, "get_cost") else 0.0

    # Optionally skip nodes with no usage
    if skip_empty and usage.total_tokens == 0:
        return

    cost_str = f" (${cost:.4f})" if cost and cost > 0 else ""

    # Display node info
    print(f"{indent}{connector}{node.name} [{node.node_type}]")
    print(
        f"{indent}{'    ' if is_last else '│   '}├─ Total: {usage.total_tokens:,} tokens{cost_str}"
    )
    print(f"{indent}{'    ' if is_last else '│   '}├─ Input: {usage.input_tokens:,}")
    print(f"{indent}{'    ' if is_last else '│   '}└─ Output: {usage.output_tokens:,}")

    # If node has model info, show it
    if node.usage.model_name:
        model_str = node.usage.model_name
        if node.usage.model_info and node.usage.model_info.provider:
            model_str += f" ({node.usage.model_info.provider})"
        print(f"{indent}{'    ' if is_last else '│   '}   Model: {model_str}")

    # Process children
    if node.children:
        print(f"{indent}{'    ' if is_last else '│   '}")
        child_indent = indent + ("    " if is_last else "│   ")
        for i, child in enumerate(node.children):
            display_node_tree(
                child,
                child_indent,
                i == len(node.children) - 1,
                context=context,
                skip_empty=skip_empty,
            )


async def display_run_tree(context: Context, name: str):
    """Display the agent workflow tree with token usage"""
    if not context.token_counter:
        print("\nNo token counter available")
        return

    # Find the agent workflow node by name
    node = await context.token_counter.find_node(name)

    if not node:
        print(f"\nAgent workflow '{name}' not found in token tree")
        return

    print("\n" + "=" * 60)
    print(f"{name} USAGE TREE")
    print("=" * 60)
    print()

    display_node_tree(node, context=context)


if __name__ == "__main__":
    import time

    start = time.time()
    asyncio.run(example_usage())
    end = time.time()
    t = end - start

    print(f"Total run time: {t:.2f}s")
