import asyncio
import os
from uuid import uuid4
from temporalio import workflow
from mcp_agent.core.context import get_current_context
from mcp_agent.workflows.llm.augmented_llm import RequestParams
from mcp_agent.workflows.llm.augmented_llm_openai import OpenAIAugmentedLLM
from mcp_agent.agents.agent import Agent
from temporalio.client import Client
from mcp_agent.executor.temporal.plugin import MCPAgentPlugin
from mcp_agent.app import MCPApp
from temporalio.worker import Worker
from mcp_agent.workflows.orchestrator.orchestrator import Orchestrator

app = MCPApp(name="mcp_basic_agent")


@workflow.defn
class OrchestratorWorkflow:
    @workflow.run
    async def run(self, prompt: str) -> str:
        context = get_current_context()

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

        result = await orchestrator.generate_str(
            message=prompt,
            request_params=RequestParams(model="gpt-4o", max_iterations=100),
        )

        return result


async def main():
    async with app.run() as running_app:
        plugin = MCPAgentPlugin(running_app)

        client = await Client.connect(
            running_app.config.temporal.host,
            plugins=[plugin],
        )

        async with Worker(
            client,
            task_queue=running_app.config.temporal.task_queue,
            workflows=[OrchestratorWorkflow],
        ):
            running_app.context.config.mcp.servers["filesystem"].args.extend(
                [os.getcwd()]
            )

            task = """Load the student's short story from short_story.md, 
            and generate a report with feedback across proofreading, 
            factuality/logical consistency and style adherence. Use the style rules from 
            https://owl.purdue.edu/owl/research_and_citation/apa_style/apa_formatting_and_style_guide/general_format.html.
            Write the graded report to graded_report.md as soon as you complete your task. Don't take too many steps."""

            output = await client.execute_workflow(
                OrchestratorWorkflow.run,
                task,
                id=f"basic-workflow-{uuid4()}",
                task_queue=running_app.config.temporal.task_queue,
            )
            print(output)


if __name__ == "__main__":
    asyncio.run(main())
