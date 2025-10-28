"""
Hello World MCP App Example

This example demonstrates a very basic MCP app that defines two tools using the
`@app.tool` and `@app.async_tool` decorators:

1. hello_world: Uses `@app.tool` decorator to create a tool that returns its result immediately.
2. hello_world_async: Uses `@app.async_tool` decorator to create an asynchronous tool that starts
   a workflow run; the result can be retrieved from the workflow status later.

"""

import asyncio
import os
from typing import Optional

from mcp_agent.agents.agent import Agent
from mcp_agent.app import MCPApp
from mcp_agent.core.context import Context as AppContext
from mcp_agent.executor.workflow import Workflow, WorkflowResult
from mcp_agent.server.app_server import create_mcp_server_for_app
from mcp_agent.workflows.llm.augmented_llm_openai import OpenAIAugmentedLLM
from mcp_agent.workflows.parallel.parallel_llm import ParallelLLM

app = MCPApp(name="hello_world")


@app.workflow
class BasicAgentWorkflow(Workflow[str]):
    """
    A basic workflow that demonstrates how to create a simple agent.
    This workflow is used as an example of a basic agent configuration.
    """

    @app.workflow_run
    async def run(self, input: str) -> WorkflowResult[str]:
        """
        Run the basic agent workflow.

        Args:
            input: The input string to prompt the agent.

        Returns:
            WorkflowResult containing the processed data.
        """

        context = app.context
        logger = context.logger

        logger.info("Current config:", data=context.config.model_dump())
        await context.info(
            f"[BasicAgentWorkflow] Received input: {input}",
        )

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

        async with finder_agent:
            logger.info("finder: Connected to server, calling list_tools...")
            result = await finder_agent.list_tools()
            await context.info(
                f"[BasicAgentWorkflow][finder_agent] Tools available: {result.model_dump_json()}",
            )

            llm = await finder_agent.attach_llm(OpenAIAugmentedLLM)

            result = await llm.generate_str(
                message=input,
            )
            logger.info(f"Input: {input}, Result: {result}")

            # Multi-turn conversations
            result = await llm.generate_str(
                message="Summarize previous response in a 128 character tweet",
            )
            await context.info(f"[BasicAgentWorkflow] Paragraph as a tweet: {result}")
            return WorkflowResult(value=result)


# (Preferred) Tool decorators
## The @app.tool decorator creates tools that return results immediately
@app.tool
async def grade_story(story: str, app_ctx: Optional[AppContext] = None) -> str:
    """
    This tool can be used to grade a student's short story submission and generate a report.
    It uses multiple agents to perform different tasks in parallel.
    The agents include:
    - Proofreader: Reviews the story for grammar, spelling, and punctuation errors.
    - Fact Checker: Verifies the factual consistency within the story.
    - Grader: Compiles the feedback from the other agents into a structured report.

    Args:
        story: The student's short story to grade
        app_ctx: Optional MCPApp context for accessing app resources and logging
    """
    # Use the context's app if available for proper logging with upstream_session
    context = app_ctx or app.context
    await context.info(f"[grade_story] Received input: {story}")

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

    grader = Agent(
        name="grader",
        instruction="""Compile the feedback from the Proofreader, Fact Checker, and Style Enforcer
        into a structured report. Summarize key issues and categorize them by type. 
        Provide actionable recommendations for improving the story, 
        and give an overall grade based on the feedback.""",
    )

    parallel = ParallelLLM(
        fan_in_agent=grader,
        fan_out_agents=[proofreader, fact_checker],
        llm_factory=OpenAIAugmentedLLM,
        context=app_ctx if app_ctx else app.context,
    )

    try:
        result = await parallel.generate_str(
            message=f"Student short story submission: {story}",
        )
    except Exception as e:
        await context.error(f"[grade_story] Error generating result: {e}")
        return ""

    if not result:
        await context.error("[grade_story] No result from parallel LLM")
        return ""
    else:
        await context.info(f"[grade_story] Result: {result}")
        return result


## The @app.async_tool decorator creates tools that start workflows asynchronously
@app.async_tool(name="grade_story_async")
async def grade_story_async(story: str, app_ctx: Optional[AppContext] = None) -> str:
    """
    Async variant of grade_story that starts a workflow run and returns IDs.
    Args:
        story: The student's short story to grade
        app_ctx: Optional MCPApp context for accessing app resources and logging
    """

    # Use the context's app if available for proper logging with upstream_session
    context = app_ctx or app.context
    await context.info(f"[grade_story_async] Received input: {story}")

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
        context=app_ctx if app_ctx else app.context,
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
