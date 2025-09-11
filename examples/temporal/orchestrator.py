"""
Example of using Temporal as the execution engine for MCP Agent workflows.
This example demonstrates how to create a workflow using the app.workflow and app.workflow_run
decorators, and how to run it using the Temporal executor.
"""

import asyncio
import os
from typing import Optional

from main import app

from mcp_agent.agents.agent import Agent
from mcp_agent.core.context import Context as AppContext
from mcp_agent.executor.temporal import TemporalExecutor
from mcp_agent.workflows.llm.augmented_llm import RequestParams
from mcp_agent.workflows.llm.augmented_llm_openai import OpenAIAugmentedLLM
from mcp_agent.workflows.orchestrator.orchestrator import Orchestrator

"""
A more complex example that demonstrates how to orchestrate multiple agents.
This example uses the @app.async_tool decorator instead of traditional workflow/run definitions
and will have a workflow created behind the scenes.
"""


@app.async_tool(name="OrchestratorWorkflow")
async def run_orchestrator(input: str, app_ctx: Optional[AppContext] = None) -> str:
    """
    Run the workflow, processing the input data.

    Args:
        input: Task description or instruction text.

    Returns:
        A WorkflowResult containing the processed data
    """

    context = app_ctx or app.context
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
        instruction="""Review the short story for grammar, spelling, and punctuation errors.
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
        context=context,
    )

    return await orchestrator.generate_str(
        message=input,
        request_params=RequestParams(model="gpt-4o", max_iterations=100),
    )


async def main():
    async with app.run() as orchestrator_app:
        executor: TemporalExecutor = orchestrator_app.executor

        task = """Load the student's short story from short_story.md, 
        and generate a report with feedback across proofreading, 
        factuality/logical consistency and style adherence. Use the style rules from 
        https://owl.purdue.edu/owl/research_and_citation/apa_style/apa_formatting_and_style_guide/general_format.html.
        Write the graded report to graded_report.md as soon as you complete your task. Don't take too many steps."""

        handle = await executor.start_workflow(
            "OrchestratorWorkflow",
            task,
        )
        a = await handle.result()
        print(a)


if __name__ == "__main__":
    asyncio.run(main())
