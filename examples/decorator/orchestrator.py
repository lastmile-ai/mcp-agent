"""
Example showing how to use the orchestrator functionality with the decorator API.
This demonstrates creating multiple agents and an orchestrator to coordinate them.
"""

import asyncio
from mcp_agent.core.decorator_app import MCPAgentDecorator
from mcp_agent.workflows.llm.augmented_llm import RequestParams

# Create the application
agent_app = MCPAgentDecorator("Orchestrator Example")


# Define worker agents
@agent_app.agent(
    name="finder",
    instruction="""You are an agent with access to the filesystem, 
            as well as the ability to fetch URLs. Your job is to identify 
            the closest match to a user's request, make the appropriate tool calls, 
            and return the URI and CONTENTS of the closest match.""",
    servers=["fetch", "filesystem"],
)
@agent_app.agent(
    name="writer",
    instruction="""You are an agent that can write to the filesystem.
            You are tasked with taking the user's input, addressing it, and 
            writing the result to disk in the appropriate location.""",
    servers=["filesystem"],
)
@agent_app.agent(
    name="proofreader",
    instruction=""""Review the short story for grammar, spelling, and punctuation errors.
            Identify any awkward phrasing or structural issues that could improve clarity. 
            Provide detailed feedback on corrections.""",
    servers=["fetch"],
)
# Define the orchestrator to coordinate the other agents
@agent_app.orchestrator(
    name="document_processor",
    instruction="""Load the student's short story from short_story.md, 
    and generate a report with feedback across proofreading, 
    factuality/logical consistency and style adherence. Use the style rules from 
    https://apastyle.apa.org/learn/quick-guide-on-formatting and 
    https://apastyle.apa.org/learn/quick-guide-on-references.
    Write the graded report to graded_report.md in the same directory as short_story.md""",
    agents=["finder", "writer", "proofreader"],
    model="haiku",  # Orchestrators typically need more capable models
)
async def main():
    async with agent_app.run() as agent:
        # The orchestrator can be used just like any other agent
        task = (
            """Load the student's short story from short_story.md, 
        and generate a report with feedback across proofreading, 
        factuality/logical consistency and style adherence. Use the style rules from 
        https://apastyle.apa.org/learn/quick-guide-on-formatting and 
        https://apastyle.apa.org/learn/quick-guide-on-references.
        Write the graded report to graded_report.md in the same directory as short_story.md""",
        )

        # Send the task
        await agent.agents["document_processor"].generate_str(
            task, request_params=RequestParams(model="claude-3-5-sonnet-latest")
        )


#

if __name__ == "__main__":
    asyncio.run(main())
