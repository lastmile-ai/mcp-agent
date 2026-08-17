"""Tests for the default (non-streaming) AugmentedLLM.generate_stream behavior."""

import pytest

from mcp_agent.workflows.llm.augmented_llm import AugmentedLLM


class NonStreamingLLM(AugmentedLLM[str, str]):
    """An AugmentedLLM subclass that only implements the non-streaming methods."""

    async def generate(self, message, request_params=None):
        return ["response"]

    async def generate_str(self, message, request_params=None):
        return "response"

    async def generate_structured(self, message, response_model, request_params=None):
        return response_model()


class TestNonStreamingAugmentedLLM:
    """Subclasses should not be forced to implement streaming."""

    @pytest.fixture
    def llm(self, mock_context):
        return NonStreamingLLM(name="test", context=mock_context)

    def test_subclass_without_generate_stream_is_instantiable(self, llm):
        """generate_stream has a default implementation, so it must not be abstract."""
        assert isinstance(llm, AugmentedLLM)

    @pytest.mark.asyncio
    async def test_generate_stream_raises_not_implemented(self, llm):
        """Iterating the default generate_stream surfaces a clear error."""
        with pytest.raises(NotImplementedError):
            async for _ in llm.generate_stream("Hello"):
                pass

    @pytest.mark.asyncio
    async def test_generate_str_stream_raises_not_implemented(self, llm):
        """The convenience wrapper propagates the same error."""
        with pytest.raises(NotImplementedError):
            async for _ in llm.generate_str_stream("Hello"):
                pass
