"""
Observability Example MCP App

This example demonstrates a very basic MCP app with observability features using OpenTelemetry.

mcp-agent automatically instruments workflows (runs, tasks/activities), tool calls, LLM calls, and more,
allowing you to trace and monitor the execution of your app. You can also add custom tracing spans as needed.

"""

import asyncio
from typing import List, Optional

from opentelemetry import trace

from mcp_agent.agents.agent import Agent
from mcp_agent.app import MCPApp
from mcp_agent.core.context import Context as AppContext
from mcp_agent.executor.workflow import Workflow
from mcp_agent.server.app_server import create_mcp_server_for_app
from mcp_agent.workflows.llm.augmented_llm_openai import OpenAIAugmentedLLM
from mcp_agent.workflows.parallel.parallel_llm import ParallelLLM

app = MCPApp(name="observability_example_app")


# You can always explicitly trace using opentelemetry as usual
def get_magic_number(original_number: int = 0) -> int:
    tracer = trace.get_tracer(__name__)
    with tracer.start_as_current_span("some_tool_function") as span:
        span.set_attribute("example.attribute", "value")
        result = 42 + original_number
        span.set_attribute("result", result)
        return result


# Workflows (runs, tasks/activities), tool calls, LLM calls, etc. are automatically traced by mcp-agent
@app.workflow_task()
async def gather_sources(query: str) -> list[str]:
    app.context.logger.info("Gathering sources", data={"query": query})
    return [f"https://example.com/search?q={query}"]


@app.workflow
class ResearchWorkflow(Workflow[None]):
    @app.workflow_run
    async def run(self, topic: str) -> List[str]:
        sources = await self.context.executor.execute(gather_sources, topic)
        self.context.logger.info(
            "Workflow completed", data={"topic": topic, "sources": sources}
        )
        return sources


@app.async_tool(name="grade_story_async")
async def grade_story_async(story: str, app_ctx: Optional[AppContext] = None) -> str:
    """
    Async variant of grade_story that starts a workflow run and returns IDs.
    Args:
        story: The student's short story to grade
        app_ctx: Optional MCPApp context for accessing app resources and logging
    """

    context = app_ctx or app.context
    await context.info(f"[grade_story_async] Received input: {story}")

    magic_number = get_magic_number(10)
    await context.info(f"[grade_story_async] Magic number computed: {magic_number}")

    proofreader = Agent(
        name="proofreader",
        instruction="""Review the short story for grammar, spelling, and punctuation errors.
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
        instruction="""Compile the feedback from the Proofreader and Fact Checker
        into a structured report. Summarize key issues and categorize them by type. 
        Provide actionable recommendations for improving the story, 
        and give an overall grade based on the feedback.""",
    )

    parallel = ParallelLLM(
        fan_in_agent=grader,
        fan_out_agents=[proofreader, fact_checker, style_enforcer],
        llm_factory=OpenAIAugmentedLLM,
        context=context,
    )

    await context.info("[grade_story_async] Starting parallel LLM")

    try:
        result = await parallel.generate_str(
            message=f"Student short story submission: {story}",
        )
    except Exception as e:
        await context.error(f"[grade_story_async] Error generating result: {e}")
        return ""

    if not result:
        await context.error("[grade_story_async] No result from parallel LLM")
        return ""

    return result


# NOTE: This main function is useful for local testing but will be ignored in the cloud deployment.
async def main():
    async with app.run() as agent_app:
        mcp_server = create_mcp_server_for_app(agent_app)
        await mcp_server.run_sse_async()


if __name__ == "__main__":
    asyncio.run(main())
