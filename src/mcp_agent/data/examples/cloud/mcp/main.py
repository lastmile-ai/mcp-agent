"""
MCP Server Example

This example demonstrates MCP primitives integration in mcp-agent within a basic agent server
that can be deployed to the cloud. It includes:
- Defining tools using the `@app.tool` and `@app.async_tool` decorators
- Creating workflow tools using the `@app.workflow` and `@app.workflow_run` decorators
- Sampling to upstream session
- Elicitation to upstream clients
- Sending notifications to upstream clients

"""

import asyncio
import os
from typing import Optional

from mcp.server.fastmcp import Context, FastMCP
from mcp.types import (
    Icon,
    ModelHint,
    ModelPreferences,
    PromptMessage,
    TextContent,
    SamplingMessage,
)
from pydantic import BaseModel, Field

from mcp_agent.agents.agent import Agent
from mcp_agent.app import MCPApp
from mcp_agent.core.context import Context as AppContext
from mcp_agent.executor.workflow import Workflow, WorkflowResult
from mcp_agent.human_input.console_handler import console_input_callback
from mcp_agent.server.app_server import create_mcp_server_for_app
from mcp_agent.workflows.llm.augmented_llm import RequestParams
from mcp_agent.workflows.llm.augmented_llm_openai import OpenAIAugmentedLLM
from mcp_agent.workflows.parallel.parallel_llm import ParallelLLM

# NOTE: This is purely optional:
# if not provided, a default FastMCP server will be created by MCPApp using create_mcp_server_for_app()
mcp = FastMCP(name="basic_agent_server", instructions="My basic agent server example.")

# Define the MCPApp instance. The server created for this app will advertise the
# MCP logging capability and forward structured logs upstream to connected clients.
app = MCPApp(
    name="basic_agent_server",
    description="Basic agent server example",
    mcp=mcp,
    human_input_callback=console_input_callback,  # enable approval prompts for local sampling
)


# region TOOLS


# Workflow Tools
## @app.workflow_run will produce a tool (workflows-BasicAgentWorkflow-run) to run the workflow
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

        logger = app.logger
        context = app.context

        logger.info("Current config:", data=context.config.model_dump())
        logger.info(
            f"Received input: {input}",
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
            logger.info("Tools available:", data=result.model_dump())

            llm = await finder_agent.attach_llm(OpenAIAugmentedLLM)

            result = await llm.generate_str(
                message=input,
            )
            logger.info(f"Input: {input}, Result: {result}")

            # Multi-turn conversations
            result = await llm.generate_str(
                message="Summarize previous response in a 128 character tweet",
                # You can configure advanced options by setting the request_params object
                request_params=RequestParams(
                    # See https://modelcontextprotocol.io/docs/concepts/sampling#model-preferences for more details
                    modelPreferences=ModelPreferences(
                        costPriority=0.1,
                        speedPriority=0.2,
                        intelligencePriority=0.7,
                    ),
                    # You can also set the model directly using the 'model' field
                    # Generally request_params type aligns with the Sampling API type in MCP
                ),
            )
            logger.info(f"Paragraph as a tweet: {result}")
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
    await context.info(f"grade_story: Received input: {story}")

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
        await context.error(f"grade_story: Error generating result: {e}")
        return ""

    if not result:
        await context.error("grade_story: No result from parallel LLM")
        return ""
    else:
        await context.info(f"grade_story: Result: {result}")
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
    logger = context.logger
    logger.info(f"grade_story_async: Received input: {story}")

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

    logger.info("grade_story_async: Starting parallel LLM")

    try:
        result = await parallel.generate_str(
            message=f"Student short story submission: {story}",
        )
    except Exception as e:
        logger.error(f"grade_story_async: Error generating result: {e}")
        return ""

    if not result:
        logger.error("grade_story_async: No result from parallel LLM")
        return ""

    return result


# region Sampling
@app.tool(
    name="sampling_demo",
    title="Sampling Demo",
    description="Perform an example of sampling.",
    annotations={"idempotentHint": False},
    icons=[Icon(src="emoji:crystal_ball")],
    meta={"category": "demo", "feature": "sampling"},
)
async def sampling_demo(
    topic: str,
    app_ctx: Optional[AppContext] = None,
) -> str:
    """
    Demonstrate MCP sampling.

    - In asyncio (no upstream client), this triggers local sampling with a human approval prompt.
    - When an MCP client is connected, the sampling request is proxied upstream.
    """
    context = app_ctx or app.context
    haiku = await context.upstream_session.create_message(
        messages=[
            SamplingMessage(
                role="user",
                content=TextContent(type="text", text=f"Write a haiku about {topic}."),
            )
        ],
        system_prompt="You are a poet.",
        max_tokens=80,
        model_preferences=ModelPreferences(
            hints=[ModelHint(name="gpt-4o-mini")],
            costPriority=0.1,
            speedPriority=0.8,
            intelligencePriority=0.1,
        ),
    )

    context.logger.info(f"Haiku: {haiku.content.text}")
    return "Done!"


# region Elicitation
@app.tool()
async def book_table(date: str, party_size: int, app_ctx: Context) -> str:
    """Book a table with confirmation"""

    # Schema must only contain primitive types (str, int, float, bool)
    class ConfirmBooking(BaseModel):
        confirm: bool = Field(description="Confirm booking?")
        notes: str = Field(default="", description="Special requests")

    context = app_ctx or app.context

    context.logger.info(
        f"Confirming the user wants to book a table for {party_size} on {date} via elicitation"
    )

    result = await context.upstream_session.elicit(
        message=f"Confirm booking for {party_size} on {date}?",
        requestedSchema=ConfirmBooking.model_json_schema(),
    )

    context.logger.info(f"Result from confirmation: {result}")

    if result.action == "accept":
        data = ConfirmBooking.model_validate(result.content)
        if data.confirm:
            return f"Booked! Notes: {data.notes or 'None'}"
        return "Booking cancelled"
    elif result.action == "decline":
        return "Booking declined"
    elif result.action == "cancel":
        return "Booking cancelled"


# region Notifications
@app.tool(name="notify_resources")
async def notify_resources(
    app_ctx: Optional[AppContext] = None,
) -> str:
    """Trigger a non-logging resource list changed notification."""
    context = app_ctx or app.context
    upstream = getattr(context, "upstream_session", None)
    if upstream is None:
        message = "No upstream session to notify"
        await context.warning(message)
        return "no-upstream"
    await upstream.send_resource_list_changed()
    log_message = "Sent notifications/resources/list_changed"
    await context.info(log_message)
    return "ok"


@app.tool(name="notify_progress")
async def notify_progress(
    progress: float = 0.5,
    message: str | None = "Asyncio progress demo",
    app_ctx: Optional[AppContext] = None,
) -> str:
    """Trigger a progress notification."""
    context = app_ctx or app.context

    await context.report_progress(
        progress=progress,
        total=1.0,
        message=message,
    )

    return "ok"


# region Prompts
@mcp.prompt()
def grade_short_story(story: str) -> list[PromptMessage]:
    return [
        PromptMessage(
            role="user",
            content=TextContent(
                type="text",
                text=f"Please grade the following short story:\n\n{story}",
            ),
        ),
    ]


# region Resources
@mcp.resource("file://short_story.md")
def get_example_short_story() -> str:
    with open(
        os.path.join(os.path.dirname(__file__), "short_story.md"), "r", encoding="utf-8"
    ) as f:
        return f.read()


# NOTE: This main function is useful for local testing but will be ignored in the cloud deployment.
async def main():
    async with app.run() as agent_app:
        # Add the current directory to the filesystem server's args if needed
        context = agent_app.context
        if "filesystem" in context.config.mcp.servers:
            context.config.mcp.servers["filesystem"].args.extend([os.getcwd()])

        agent_app.logger.info(f"Creating MCP server for {agent_app.name}")
        agent_app.logger.info("Registered workflows:")
        for workflow_id in agent_app.workflows:
            agent_app.logger.info(f"  - {workflow_id}")

        # This will reuse the FastMCP server defined in the MCPApp instance or
        # create a new one if none was provided.
        mcp_server = create_mcp_server_for_app(agent_app)
        agent_app.logger.info(f"MCP Server settings: {mcp_server.settings}")

        await mcp_server.run_sse_async()


if __name__ == "__main__":
    asyncio.run(main())
