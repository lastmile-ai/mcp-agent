"""
Example of using Temporal as the execution engine for MCP Agent workflows.
This example demonstrates how to create a workflow using the app.workflow and app.workflow_run
decorators, and how to run it using the Temporal executor.
"""

import asyncio

from mcp_agent.agents.agent import Agent
from mcp_agent.executor.temporal import TemporalExecutor
from mcp_agent.executor.workflow import Workflow, WorkflowResult
from mcp_agent.workflows.llm.augmented_llm_openai import OpenAIAugmentedLLM
from mcp_agent.workflows.parallel.parallel_llm import ParallelLLM
from mcp_agent.tracing.token_counter import TokenSummary
from mcp_agent.core.context import Context

from main import app

SHORT_STORY = """
The Battle of Glimmerwood

In the heart of Glimmerwood, a mystical forest knowed for its radiant trees, a small village thrived. 
The villagers, who were live peacefully, shared their home with the forest's magical creatures, 
especially the Glimmerfoxes whose fur shimmer like moonlight.

One fateful evening, the peace was shaterred when the infamous Dark Marauders attack. 
Lead by the cunning Captain Thorn, the bandits aim to steal the precious Glimmerstones which was believed to grant immortality.

Amidst the choas, a young girl named Elara stood her ground, she rallied the villagers and devised a clever plan.
Using the forests natural defenses they lured the marauders into a trap. 
As the bandits aproached the village square, a herd of Glimmerfoxes emerged, blinding them with their dazzling light, 
the villagers seized the opportunity to captured the invaders.

Elara's bravery was celebrated and she was hailed as the "Guardian of Glimmerwood". 
The Glimmerstones were secured in a hidden grove protected by an ancient spell.

However, not all was as it seemed. The Glimmerstones true power was never confirm, 
and whispers of a hidden agenda linger among the villagers.
"""


@app.workflow
class ParallelWorkflow(Workflow[str]):
    """
    A simple workflow that demonstrates the basic structure of a Temporal workflow.
    """

    @app.workflow_run
    async def run(self, input: str) -> WorkflowResult[str]:
        """
        Run the workflow, processing the input data.

        Args:
            input_data: The data to process

        Returns:
            A WorkflowResult containing the processed data
        """

        proofreader = Agent(
            name="proofreader",
            instruction=""""Review the short story for grammar, spelling, and punctuation errors.
            Identify any awkward phrasing or structural issues that could improve clarity. 
            Provide detailed feedback on corrections.""",
        )

        fact_checker = Agent(
            name="fact_checker",
            instruction="""Verify the factual consistency within the story. Identify any contradictions,
            logical inconsistencies, or inaccuracies in the plot, character actions, or setting. 
            Highlight potential issues with reasoning or coherence.""",
        )

        style_enforcer = Agent(
            name="style_enforcer",
            instruction="""Analyze the story for adherence to style guidelines.
            Evaluate the narrative flow, clarity of expression, and tone. Suggest improvements to 
            enhance storytelling, readability, and engagement.""",
        )

        grader = Agent(
            name="grader",
            instruction="""Compile the feedback from the Proofreader, Fact Checker, and Style Enforcer
            into a structured report. Summarize key issues and categorize them by type. 
            Provide actionable recommendations for improving the story, 
            and give an overall grade based on the feedback.""",
        )

        parallel = ParallelLLM(
            fan_in_agent=grader,
            fan_out_agents=[proofreader, fact_checker, style_enforcer],
            llm_factory=OpenAIAugmentedLLM,
            context=app.context,
        )

        result = await parallel.generate_str(
            message=f"Student short story submission: {input}",
        )

        # Get token usage information
        metadata = {}
        if hasattr(parallel, "get_token_node"):
            token_node = await parallel.get_token_node()
            if token_node:
                metadata["token_usage"] = token_node.get_usage()
                metadata["token_cost"] = token_node.get_cost()
                metadata["token_tree"] = token_node.format_tree()

        return WorkflowResult(value=result, metadata=metadata)


async def display_token_summary(context: Context):
    """Display comprehensive token usage summary"""
    if not context.token_counter:
        print("\nNo token counter available")
        return

    summary: TokenSummary = await context.token_counter.get_summary()

    print("\n" + "=" * 60)
    print("TOKEN USAGE SUMMARY")
    print("=" * 60)

    # Display usage tree using the root node directly
    root_node = await context.token_counter.get_app_node()
    if root_node:
        print("\nToken Usage Tree:")
        print("-" * 40)
        print(root_node.format_tree())

        # Display cost for the root node
        total_cost = root_node.get_cost()
        if total_cost > 0:
            print(f"\nTotal cost from tree: ${total_cost:.4f}")

    # Total usage
    print("\nTotal Usage:")
    print(f"  Total tokens: {summary.usage.total_tokens:,}")
    print(f"  Input tokens: {summary.usage.input_tokens:,}")
    print(f"  Output tokens: {summary.usage.output_tokens:,}")
    print(f"  Total cost: ${summary.cost:.4f}")

    # Breakdown by model
    if summary.model_usage:
        print("\nBreakdown by Model:")
        for model_key, data in summary.model_usage.items():
            print(f"  {model_key}:")
            print(
                f"    Tokens: {data.usage.total_tokens:,} (input: {data.usage.input_tokens:,}, output: {data.usage.output_tokens:,})"
            )
            print(f"    Cost: ${data.cost:.4f}")

    print("\n" + "=" * 60)


async def main():
    async with app.run() as orchestrator_app:
        executor: TemporalExecutor = orchestrator_app.executor

        handle = await executor.start_workflow(
            "ParallelWorkflow",
            SHORT_STORY,
        )
        result = await handle.result()
        print("\n=== WORKFLOW RESULT ===")
        print(result.value)

        # Display token information from workflow metadata if available
        if result.metadata and "token_tree" in result.metadata:
            print("\n=== WORKFLOW TOKEN USAGE ===")
            print(result.metadata["token_tree"])
            if "token_cost" in result.metadata:
                print(f"\nWorkflow Cost: ${result.metadata['token_cost']:.4f}")
            if "token_usage" in result.metadata:
                usage = result.metadata["token_usage"]
                print(
                    f"Workflow Tokens: {usage.total_tokens:,} (input: {usage.input_tokens:,}, output: {usage.output_tokens:,})"
                )

        # Query the running workflow for its in-process token usage
        try:
            remote_tree = await handle.query("token_tree")
            remote_summary = await handle.query("token_summary")

            print("\n=== WORKFLOW TOKEN USAGE (queried) ===")
            if isinstance(remote_tree, str):
                print(remote_tree)
            if isinstance(remote_summary, dict):
                tu = remote_summary.get("total_usage", {})
                print(
                    f"\nTotal (queried): {tu.get('total_tokens', 0):,} (input: {tu.get('input_tokens', 0):,}, output: {tu.get('output_tokens', 0):,})"
                )
                print(
                    f"Total cost (queried): ${remote_summary.get('total_cost', 0.0):.4f}"
                )
        except Exception:
            # Queries may be unavailable if worker didn't register them; ignore
            pass

        # The local context's token counter reflects the client process and may be 0 under Temporal.
        # We rely on the queried workflow metrics above instead of local TokenCounter here.


if __name__ == "__main__":
    import time

    start = time.time()
    asyncio.run(main())
    end = time.time()
    t = end - start

    print(f"\nTotal run time: {t:.2f}s")
