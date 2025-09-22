"""
Example demonstrating how to use the elicitation-based human input handler
for Temporal workflows.

This example shows how the new handler enables LLMs to request user input
when running in Temporal workflows by routing requests through the MCP
elicitation framework instead of direct console I/O.
"""

import asyncio
from mcp_agent.app import MCPApp
from mcp_agent.human_input.elicitation_handler import elicitation_input_callback

from mcp_agent.agents.agent import Agent
from mcp_agent.core.context import Context
from mcp_agent.server.app_server import create_mcp_server_for_app
from mcp_agent.workflows.llm.augmented_llm_openai import OpenAIAugmentedLLM


# Create a single FastMCPApp instance (which extends MCPApp)
# We don't need to explicitly create a tool for human interaction; providing the human_input_callback will
# automatically create a tool for the agent to use.
app = MCPApp(
    name="basic_agent_server",
    description="Basic agent server example",
    human_input_callback=elicitation_input_callback,  # Use elicitation handler for human input in temporal workflows
)


@app.tool
async def greet(app_ctx: Context | None = None) -> str:
    """
    Run the basic agent workflow using the app.tool decorator to set up the workflow.
    The code in this function is run in workflow context.
    LLM calls are executed in the activity context.
    You can use the app_ctx to access the executor to run activities explicitly.
    Functions decorated with @app.workflow_task will be run in activity context.

    Args:
        input: none

    Returns:
        str: The greeting result from the agent
    """

    app = app_ctx.app

    logger = app.logger
    logger.info("[workflow-mode] Running greet_tool")

    greeting_agent = Agent(
        name="greeter",
        instruction="""You are a friendly assistant.""",
        server_names=[],
    )

    async with greeting_agent:
        finder_llm = await greeting_agent.attach_llm(OpenAIAugmentedLLM)

        result = await finder_llm.generate_str(
            message="Ask the user for their name and greet them.",
        )
        logger.info("[workflow-mode] greet_tool agent result", data={"result": result})

    return result


async def main():
    async with app.run() as agent_app:
        # Log registered workflows and agent configurations
        agent_app.logger.info(f"Creating MCP server for {agent_app.name}")

        agent_app.logger.info("Registered workflows:")
        for workflow_id in agent_app.workflows:
            agent_app.logger.info(f"  - {workflow_id}")
        # Create the MCP server that exposes both workflows and agent configurations
        mcp_server = create_mcp_server_for_app(agent_app)

        # Run the server
        await mcp_server.run_sse_async()


if __name__ == "__main__":
    asyncio.run(main())
