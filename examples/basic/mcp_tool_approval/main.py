import asyncio
import os
from pathlib import Path

from mcp_agent.agents.agent import Agent
from mcp_agent.app import MCPApp
from mcp_agent.workflows.llm.augmented_llm_openai import OpenAIAugmentedLLM

from policy_gateway import (
    ApprovalGate,
    ApprovalHook,
    JsonlAuditSink,
    console_approval,
    filesystem_policy,
)

app = MCPApp(name="mcp_tool_approval")


class ApprovalOpenAIAugmentedLLM(ApprovalHook, OpenAIAugmentedLLM):
    def __init__(self, *args, approval_gate: ApprovalGate, **kwargs):
        super().__init__(*args, **kwargs)
        self.approval_gate = approval_gate


@app.tool()
async def example_usage() -> str:
    async with app.run() as agent_app:
        agent_app.context.config.mcp.servers["filesystem"].args.append(os.getcwd())

        gate = ApprovalGate(
            decide=filesystem_policy,
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
                llm_factory=lambda **kwargs: ApprovalOpenAIAugmentedLLM(
                    approval_gate=gate, **kwargs
                )
            )
            return await llm.generate_str("List the files in the workspace.")


if __name__ == "__main__":
    asyncio.run(example_usage())
