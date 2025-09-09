#!/usr/bin/env python3
"""Jupyter Notebook compatible MCP-Agent."""

from mcp_agent.app import MCPApp
from mcp_agent.agents.agent_spec import AgentSpec
from mcp_agent.workflows.factory import create_llm


class NotebookAgent:
    """MCP Agent for Jupyter Notebooks."""

    def __init__(self, name="notebook_agent", model="anthropic.haiku"):
        self.app = MCPApp(name)
        self.model = model

        # Define the agent
        self.agent_spec = AgentSpec(
            name="assistant",
            instruction="You are a helpful AI assistant for data analysis and exploration.",
            server_names=["filesystem"],
        )

        self.app.register_agent("assistant", self.agent_spec)
        self.llm = None
        self._context = None

    async def __aenter__(self):
        """Async context manager entry."""
        self._context = await self.app.run().__aenter__()

        # Parse provider from model string
        provider = "openai"
        if "." in self.model or ":" in self.model:
            provider = self.model.split(".")[0].split(":")[0]

        # Create LLM
        self.llm = create_llm(
            agent_name="assistant",
            server_names=["filesystem"],
            instruction=self.agent_spec.instruction,
            provider=provider,
            model=self.model,
            context=self.app.context,
        )

        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        if self._context:
            await self._context.__aexit__(exc_type, exc_val, exc_tb)

    async def chat(self, message: str) -> str:
        """Send a message and get a response."""
        if not self.llm:
            raise RuntimeError("Agent not initialized. Use async with statement.")
        return await self.llm.generate_str(message)

    async def analyze_file(self, filepath: str) -> str:
        """Analyze a file using the agent."""
        prompt = f"Please analyze the file at {filepath} and provide insights."
        return await self.chat(prompt)

    async def summarize_data(self, data_description: str) -> str:
        """Get a summary of data."""
        prompt = f"Please summarize this data: {data_description}"
        return await self.chat(prompt)


# Example usage in Jupyter Notebook:
#
# import asyncio
# from agent import NotebookAgent
#
# async def main():
#     async with NotebookAgent(model="anthropic.haiku") as agent:
#         response = await agent.chat("What files are in the current directory?")
#         print(response)
#
# # In Jupyter, use await directly in cells
# await main()
#
# # Or use the synchronous wrapper
# def run_agent(message, model="anthropic.haiku"):
#     async def _run():
#         async with NotebookAgent(model=model) as agent:
#             return await agent.chat(message)
#     return asyncio.run(_run())
#
# response = run_agent("List all CSV files")
# print(response)
