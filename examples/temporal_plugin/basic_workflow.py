from temporalio import workflow

with workflow.unsafe.imports_passed_through():
    from mcp_agent.workflows.llm.augmented_llm_openai import OpenAIAugmentedLLM
    from mcp_agent.agents.agent import Agent
    from mcp_agent.app import MCPApp


app = MCPApp(name="mcp_basic_agent")


@workflow.defn
class BasicWorkflow:
    @workflow.run
    async def run(self, prompt: str) -> str:
        async with app.run():
            simple_agent = Agent(
                name="finder",
                instruction="You are a helpful agent",
                server_names=["fetch"],
            )

            async with simple_agent:
                llm = await simple_agent.attach_llm(OpenAIAugmentedLLM)
                result = await llm.generate_str(prompt)
                return result
