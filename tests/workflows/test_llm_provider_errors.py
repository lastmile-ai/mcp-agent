import types

import pytest

from mcp_agent.executor.errors import WorkflowApplicationError


@pytest.mark.asyncio
async def test_execute_openai_request_non_retryable(monkeypatch):
    from mcp_agent.workflows.llm import augmented_llm_openai as mod

    class DummyError(Exception):
        pass

    async def create(**kwargs):
        raise DummyError("boom")

    dummy_client = types.SimpleNamespace(
        chat=types.SimpleNamespace(completions=types.SimpleNamespace(create=create))
    )

    monkeypatch.setattr(mod, "_NON_RETRYABLE_OPENAI_ERRORS", (DummyError,))

    with pytest.raises(WorkflowApplicationError) as excinfo:
        await mod._execute_openai_request(dummy_client, {"foo": "bar"})

    err = excinfo.value
    assert err.non_retryable is True
    assert err.type == "DummyError"


@pytest.mark.asyncio
async def test_execute_openai_request_propagates_rate_limit(monkeypatch):
    from mcp_agent.workflows.llm import augmented_llm_openai as mod

    class DummyRateLimitError(Exception):
        pass

    monkeypatch.setattr(mod, "RateLimitError", DummyRateLimitError, raising=False)

    async def create(**kwargs):
        raise mod.RateLimitError("slow down")

    dummy_client = types.SimpleNamespace(
        chat=types.SimpleNamespace(completions=types.SimpleNamespace(create=create))
    )

    with pytest.raises(mod.RateLimitError):
        await mod._execute_openai_request(dummy_client, {})


def test_raise_non_retryable_azure():
    from mcp_agent.workflows.llm import augmented_llm_azure as mod

    with pytest.raises(WorkflowApplicationError) as excinfo:
        mod._raise_non_retryable_azure(ValueError("bad"), status_code=400)

    err = excinfo.value
    assert err.non_retryable is True
    assert err.type == "ValueError"
    assert "400" in str(err)


@pytest.mark.asyncio
async def test_execute_anthropic_async_non_retryable(monkeypatch):
    from mcp_agent.workflows.llm import augmented_llm_anthropic as mod

    class DummyError(Exception):
        pass

    async def create(**kwargs):
        raise DummyError("bad")

    dummy_client = types.SimpleNamespace(messages=types.SimpleNamespace(create=create))

    monkeypatch.setattr(mod, "_NON_RETRYABLE_ANTHROPIC_ERRORS", (DummyError,))

    with pytest.raises(WorkflowApplicationError):
        await mod._execute_anthropic_async(dummy_client, {})
