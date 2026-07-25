import asyncio
import os
from pathlib import Path

from mcp.types import CallToolRequest

from mcp_agent.agents.agent import Agent
from mcp_agent.app import MCPApp
from mcp_agent.workflows.llm.augmented_llm_openai import OpenAIAugmentedLLM

from policy_gateway import (
    DefaultPolicy,
    JsonlAuditSink,
    PolicyGateway,
    console_approval,
)

app = MCPApp(name="mcp_tool_approval")


class PolicyOpenAIAugmentedLLM(OpenAIAugmentedLLM):
    def __init__(self, *args, policy_gateway: PolicyGateway, **kwargs):
        super().__init__(*args, **kwargs)
        self.policy_gateway = policy_gateway

    async def pre_tool_call(
        self, tool_call_id: str | None, request: CallToolRequest
    ) -> CallToolRequest | bool:
        if await self.policy_gateway.authorize(request, tool_call_id):
            return request
        return False


@app.tool()
async def example_usage() -> str:
    async with app.run() as agent_app:
        agent_app.context.config.mcp.servers["filesystem"].args.append(os.getcwd())

        gateway = PolicyGateway(
            policy=DefaultPolicy(),
            approval_callback=console_approval,
            audit_sink=JsonlAuditSink(Path("logs/policy-audit.jsonl")),
        )
        agent = Agent(
            name="workspace_assistant",
            instruction="List files and summarize their names. Do not modify them.",
            server_names=["filesystem"],
        )

        async with agent:
            llm = await agent.attach_llm(
                llm_factory=lambda **kwargs: PolicyOpenAIAugmentedLLM(
                    policy_gateway=gateway, **kwargs
                )
            )
            return await llm.generate_str("List the files in the workspace.")


if __name__ == "__main__":
    asyncio.run(example_usage())
