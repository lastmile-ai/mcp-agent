from temporalio import workflow
from mcp_agent.workflows.llm.augmented_llm_openai import OpenAIAugmentedLLM
from mcp_agent.agents.agent import Agent


@workflow.defn
class BasicWorkflow:
    @workflow.run
    async def run(self, prompt: str) -> str:
        simple_agent = Agent(
            name="finder",
            instruction="You are a helpful agent",
            server_names=["fetch"],
        )

        async with simple_agent:
            llm = await simple_agent.attach_llm(OpenAIAugmentedLLM)
            result = await llm.generate_str(prompt)
            return result
