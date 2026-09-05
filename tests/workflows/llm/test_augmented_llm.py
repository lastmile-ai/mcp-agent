from unittest.mock import AsyncMock, MagicMock

import pytest

from mcp_agent.workflows.llm.augmented_llm import AugmentedLLM


class StubAugmentedLLM(AugmentedLLM):
    async def generate(self, message, request_params=None):
        raise NotImplementedError

    async def generate_str(self, message, request_params=None):
        raise NotImplementedError

    async def generate_structured(self, message, response_model, request_params=None):
        raise NotImplementedError

    async def generate_stream(self, message, request_params=None):
        if False:
            yield


@pytest.mark.asyncio
async def test_get_prompt_forwards_template_arguments(mock_context):
    agent = MagicMock()
    agent.name = "review_agent"
    agent.instruction = None
    agent.get_prompt = AsyncMock()
    llm = StubAugmentedLLM(agent=agent, context=mock_context)

    await llm.get_prompt(
        name="code_review",
        arguments={"language": "python", "file": "main.py"},
        server_name="review_server",
    )

    agent.get_prompt.assert_awaited_once_with(
        name="code_review",
        arguments={"language": "python", "file": "main.py"},
        server_name="review_server",
    )


@pytest.mark.asyncio
async def test_get_prompt_preserves_positional_server_name(mock_context):
    agent = MagicMock()
    agent.name = "review_agent"
    agent.instruction = None
    agent.get_prompt = AsyncMock()
    llm = StubAugmentedLLM(agent=agent, context=mock_context)

    await llm.get_prompt("code_review", "review_server")

    agent.get_prompt.assert_awaited_once_with(
        name="code_review", arguments=None, server_name="review_server"
    )
