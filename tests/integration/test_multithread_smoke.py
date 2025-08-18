import asyncio
import concurrent.futures
from unittest.mock import AsyncMock

from mcp_agent.app import MCPApp
from mcp_agent.agents.agent import Agent

from mcp_agent.workflows.llm.augmented_llm import RequestParams, AugmentedLLM


class _MockLLM(AugmentedLLM):
    def __init__(self, agent=None, **kwargs):
        super().__init__(**kwargs)
        self.agent = agent
        self.generate_mock = AsyncMock()
        self.generate_str_mock = AsyncMock()
        self.generate_structured_mock = AsyncMock()

    async def generate(self, message, request_params=None):
        return await self.generate_mock(message, request_params)

    async def generate_str(self, message, request_params=None):
        return await self.generate_str_mock(message, request_params)

    async def generate_structured(self, message, response_model, request_params=None):
        return await self.generate_structured_mock(
            message, response_model, request_params
        )


class _MockLLMFactory:
    def __call__(self, agent):
        llm = _MockLLM(agent=agent)

        async def _gen_str(message, request_params=None):
            return "hello"

        llm.generate_str_mock.side_effect = _gen_str
        llm.generate_mock.side_effect = _gen_str
        return llm


def worker_once() -> str:
    loop = asyncio.new_event_loop()
    try:
        asyncio.set_event_loop(loop)

        async def run_once():
            app = MCPApp(name="mt_smoke")
            async with app.run():
                agent = Agent(
                    name="worker", instruction="You are concise.", server_names=[]
                )
                # Ensure agent uses this app's context (avoid global context across threads)
                agent.context = app.context
                await agent.attach_llm(llm_factory=_MockLLMFactory())
                out = await agent.llm.generate_str(
                    "Say hello",
                    request_params=RequestParams(maxTokens=64, max_iterations=1),
                )
                return out

        return loop.run_until_complete(run_once())
    finally:
        loop.close()
        asyncio.set_event_loop(None)


def test_multithread_smoke_two_workers():
    # Run two workers concurrently; ensures independent event loops and app instances
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as ex:
        futures = [ex.submit(worker_once) for _ in range(2)]
        results = [f.result(timeout=20) for f in futures]
    assert all(isinstance(r, str) and len(r) > 0 for r in results)
