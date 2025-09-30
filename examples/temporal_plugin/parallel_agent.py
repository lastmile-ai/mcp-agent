import asyncio
from uuid import uuid4
from temporalio import workflow
from mcp_agent.core.context import get_current_context
from mcp_agent.workflows.llm.augmented_llm_openai import OpenAIAugmentedLLM
from mcp_agent.agents.agent import Agent
from temporalio.client import Client
from mcp_agent.executor.temporal.plugin import MCPAgentPlugin
from mcp_agent.app import MCPApp
from temporalio.worker import Worker
from mcp_agent.workflows.parallel.parallel_llm import ParallelLLM

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


app = MCPApp(name="mcp_basic_agent")


@workflow.defn
class ParallelAgentWorkflow:
    @workflow.run
    async def run(self, prompt: str) -> str:
        context = get_current_context()

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
            instruction="""Compile the feedback from the Proofreader, Fact Checker, and Style Enforcer
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

        result = await parallel.generate_str(
            message=f"Student short story submission: {prompt}",
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
            workflows=[ParallelAgentWorkflow],
        ):
            output = await client.execute_workflow(
                ParallelAgentWorkflow.run,
                args=[SHORT_STORY],
                id=f"basic-workflow-{uuid4()}",
                task_queue=running_app.config.temporal.task_queue,
            )
            print(output)


if __name__ == "__main__":
    asyncio.run(main())
