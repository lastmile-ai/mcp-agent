"""
Workflow MCP Server Example

This example demonstrates three approaches to creating agents and workflows:
1. Traditional workflow-based approach with manual agent creation
2. Programmatic agent configuration using AgentConfig
3. Declarative agent configuration using FastMCPApp decorators
"""

import argparse
import asyncio
import os
from typing import Optional

from mcp.server.fastmcp import FastMCP
from mcp_agent.core.context import Context as AppContext

from mcp_agent.app import MCPApp
from mcp_agent.server.app_server import create_mcp_server_for_app
from mcp_agent.agents.agent import Agent
from mcp_agent.workflows.llm.augmented_llm import RequestParams
from mcp_agent.workflows.llm.llm_selector import ModelPreferences
from mcp_agent.workflows.llm.augmented_llm_anthropic import AnthropicAugmentedLLM
from mcp_agent.workflows.llm.augmented_llm_openai import OpenAIAugmentedLLM
from mcp_agent.workflows.parallel.parallel_llm import ParallelLLM
from mcp_agent.executor.workflow import Workflow, WorkflowResult

# Note: This is purely optional:
# if not provided, a default FastMCP server will be created by MCPApp using create_mcp_server_for_app()
mcp = FastMCP(name="basic_agent_server", description="My basic agent server example.")

# Define the MCPApp instance. The server created for this app will advertise the
# MCP logging capability and forward structured logs upstream to connected clients.
app = MCPApp(
    name="basic_agent_server",
    description="Basic agent server example",
    mcp=mcp,
)


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

            llm = await finder_agent.attach_llm(AnthropicAugmentedLLM)

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


@app.tool
async def grade_story(story: str, app_ctx: Optional[AppContext] = None) -> str:
    """
    This tool can be used to grade a student's short story submission and generate a report.
    It uses multiple agents to perform different tasks in parallel.
    The agents include:
    - Proofreader: Reviews the story for grammar, spelling, and punctuation errors.
    - Fact Checker: Verifies the factual consistency within the story.
    - Style Enforcer: Analyzes the story for adherence to style guidelines.
    - Grader: Compiles the feedback from the other agents into a structured report.

    Args:
        story: The student's short story to grade
        app_ctx: Optional MCPApp context for accessing app resources and logging
    """
    # Use the context's app if available for proper logging with upstream_session
    _app = app_ctx.app if app_ctx else app
    # Ensure the app's logger is bound to the current context with upstream_session
    if _app._logger and hasattr(_app._logger, "_bound_context"):
        _app._logger._bound_context = app_ctx
    logger = _app.logger
    logger.info(f"grade_story: Received input: {story}")

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
        context=app_ctx if app_ctx else app.context,
    )

    try:
        result = await parallel.generate_str(
            message=f"Student short story submission: {story}",
        )
    except Exception as e:
        logger.error(f"grade_story: Error generating result: {e}")
        return None

    if not result:
        logger.error("grade_story: No result from parallel LLM")
    else:
        logger.info(f"grade_story: Result: {result}")

    return result


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--custom-fastmcp-settings",
        action="store_true",
        help="Enable custom FastMCP settings for the server",
    )
    args = parser.parse_args()
    use_custom_fastmcp_settings = args.custom_fastmcp_settings

    async with app.run() as agent_app:
        # Add the current directory to the filesystem server's args if needed
        context = agent_app.context
        if "filesystem" in context.config.mcp.servers:
            context.config.mcp.servers["filesystem"].args.extend([os.getcwd()])

        # Log registered workflows and agent configurations
        agent_app.logger.info(f"Creating MCP server for {agent_app.name}")

        agent_app.logger.info("Registered workflows:")
        for workflow_id in agent_app.workflows:
            agent_app.logger.info(f"  - {workflow_id}")

        # Create the MCP server that exposes both workflows and agent configurations,
        # optionally using custom FastMCP settings
        fast_mcp_settings = (
            {"host": "localhost", "port": 8001, "debug": True, "log_level": "DEBUG"}
            if use_custom_fastmcp_settings
            else None
        )
        mcp_server = create_mcp_server_for_app(agent_app, **(fast_mcp_settings or {}))
        agent_app.logger.info(f"MCP Server settings: {mcp_server.settings}")

        # Run the server
        await mcp_server.run_stdio_async()


if __name__ == "__main__":
    asyncio.run(main())
