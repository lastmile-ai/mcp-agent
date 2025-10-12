import asyncio
import json
import pathlib
import sys
from typing import Any, Dict

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "src"))

from mcp_agent.config import (
    AnthropicSettings,
    LLMGatewaySettings,
    LLMProviderFallback,
    OpenAISettings,
    Settings,
)
from mcp_agent.llm.events import LLMEventFanout
from mcp_agent.llm.gateway import (
    LLMCallParams,
    LLMGateway,
    LLMProviderEvent,
    LLMProviderStream,
    LLMProviderError,
    RetryableLLMProviderError,
)
from mcp_agent.workflows.llm.llm_selector import ProviderHandle


class _FakeState:
    def __init__(self) -> None:
        self.llm_streams: Dict[str, LLMEventFanout] = {}
        self.queues: Dict[str, set[asyncio.Queue[str]]] = {}
        self.runs: Dict[str, Dict[str, Any]] = {}
        self.artifacts: Dict[str, tuple[bytes, str]] = {}


class _FakeArtifactStore:
    def __init__(self) -> None:
        self.saved: list[tuple[str, str, bytes, str]] = []

    async def put(self, run_id: str, path: str, data: bytes, content_type: str = "application/json") -> str:
        self.saved.append((run_id, path, data, content_type))
        return f"mem://{run_id}/{path}"


class _Counter:
    def __init__(self) -> None:
        self.calls: list[tuple[float, Dict[str, Any] | None]] = []

    def add(self, value: float, attributes: Dict[str, Any] | None = None) -> None:
        self.calls.append((value, attributes or {}))


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


def _base_settings() -> Settings:
    return Settings(
        openai=OpenAISettings(api_key="sk-test", default_model="gpt-test"),
        llm_gateway=LLMGatewaySettings(
            llm_default_provider="openai",
            llm_default_model="gpt-test",
            llm_retry_max=1,
            llm_retry_base_ms=0,
            llm_retry_jitter_ms=0,
        ),
    )


async def _drain_events(queue: asyncio.Queue[str]) -> list[Dict[str, Any]]:
    events: list[Dict[str, Any]] = []
    while True:
        try:
            payload = queue.get_nowait()
        except asyncio.QueueEmpty:
            break
        else:
            events.append(json.loads(payload))
    return events


def _register_default_gateway(
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[_Counter, _Counter, _Counter, _Counter]:
    tokens_counter = _Counter()
    failures_counter = _Counter()
    fallback_counter = _Counter()
    budget_counter = _Counter()
    monkeypatch.setattr("mcp_agent.telemetry.llm_tokens_total", tokens_counter)
    monkeypatch.setattr("mcp_agent.telemetry.llm_failures_total", failures_counter)
    monkeypatch.setattr("mcp_agent.telemetry.llm_provider_fallback_total", fallback_counter)
    monkeypatch.setattr("mcp_agent.telemetry.llm_budget_abort_total", budget_counter)
    sse_counter = _Counter()
    monkeypatch.setattr("mcp_agent.telemetry.llm_sse_consumer_count", sse_counter)
    monkeypatch.setattr("mcp_agent.llm.events.llm_sse_consumer_count", sse_counter)
    monkeypatch.setattr("mcp_agent.llm.gateway.llm_tokens_total", tokens_counter)
    monkeypatch.setattr("mcp_agent.llm.gateway.llm_failures_total", failures_counter)
    monkeypatch.setattr("mcp_agent.llm.gateway.llm_provider_fallback_total", fallback_counter)
    monkeypatch.setattr("mcp_agent.llm.gateway.llm_budget_abort_total", budget_counter)
    return tokens_counter, failures_counter, fallback_counter, budget_counter


@pytest.mark.anyio("asyncio")
async def test_gateway_stream_success(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = _base_settings()
    state = _FakeState()
    fanout = LLMEventFanout()
    queue = await fanout.subscribe()
    state.llm_streams["run"] = fanout
    state.runs["run"] = {}
    store = _FakeArtifactStore()
    gateway = LLMGateway(settings, state=state, artifact_store=store)
    tokens_counter, failures_counter, _, _ = _register_default_gateway(monkeypatch)

    async def _factory(prompt: str, params: LLMCallParams, handle: ProviderHandle, meta: Dict[str, Any]) -> LLMProviderStream:
        async def _iterator():
            yield LLMProviderEvent(type="token", delta="Hello")
            yield LLMProviderEvent(type="token", delta=" world")
            yield LLMProviderEvent(
                type="complete",
                finish_reason="stop",
                usage={"prompt_tokens": 4, "completion_tokens": 2, "cost_usd": 0.002},
            )

        return LLMProviderStream(iterator=_iterator(), usage={"prompt_tokens": 4})

    gateway.register_provider("openai", _factory)

    params = LLMCallParams()
    result = await gateway.run(
        run_id="run",
        trace_id="trace",
        prompt="Hello world",
        params=params,
        context_hash=None,
        cancel_token=asyncio.Event(),
    )

    assert result["finish_reason"] == "stop"
    assert result["tokens_completion"] >= 2
    assert not failures_counter.calls
    assert tokens_counter.calls

    events = await _drain_events(queue)
    event_types = [evt["type"] for evt in events]
    assert event_types[0] == "llm/provider_selected"
    assert "llm/starting" in event_types
    assert "llm/complete" in event_types
    assert "llm/provider_succeeded" in event_types

    assert store.saved, "request snapshot should be persisted"
    saved_json = json.loads(store.saved[0][2].decode("utf-8"))
    assert saved_json["prompt_hash"].startswith("sha256:")


@pytest.mark.anyio("asyncio")
async def test_gateway_retries_transient_error(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = _base_settings()
    state = _FakeState()
    fanout = LLMEventFanout()
    queue = await fanout.subscribe()
    state.llm_streams["run"] = fanout
    state.runs["run"] = {}
    gateway = LLMGateway(settings, state=state, artifact_store=_FakeArtifactStore())
    _, _, _, budget_counter = _register_default_gateway(monkeypatch)

    attempts = {"count": 0}

    async def _factory(prompt: str, params: LLMCallParams, handle: ProviderHandle, meta: Dict[str, Any]) -> LLMProviderStream:
        if attempts["count"] == 0:
            attempts["count"] += 1
            raise RetryableLLMProviderError("temporary")

        async def _iterator():
            yield LLMProviderEvent(type="token", delta="Hi")
            yield LLMProviderEvent(type="complete", finish_reason="stop", usage={"completion_tokens": 1})

        return LLMProviderStream(iterator=_iterator())

    gateway.register_provider("openai", _factory)

    result = await gateway.run(
        run_id="run",
        trace_id="trace",
        prompt="Hello",
        params=LLMCallParams(),
        context_hash=None,
        cancel_token=asyncio.Event(),
    )

    assert result["finish_reason"] == "stop"
    events = await _drain_events(queue)
    assert any(evt["type"] == "llm/error" for evt in events), "should emit error before retry"


@pytest.mark.anyio("asyncio")
async def test_gateway_enforces_token_cap(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = _base_settings()
    settings.llm_gateway = LLMGatewaySettings(
        llm_default_provider="openai",
        llm_default_model="gpt-test",
        llm_tokens_cap=1,
        llm_retry_max=0,
        llm_retry_base_ms=0,
        llm_retry_jitter_ms=0,
    )
    state = _FakeState()
    fanout = LLMEventFanout()
    queue = await fanout.subscribe()
    state.llm_streams["run"] = fanout
    state.runs["run"] = {}
    gateway = LLMGateway(settings, state=state, artifact_store=_FakeArtifactStore())
    _, _, _, budget_counter = _register_default_gateway(monkeypatch)

    async def _factory(prompt: str, params: LLMCallParams, handle: ProviderHandle, meta: Dict[str, Any]) -> LLMProviderStream:
        async def _iterator():
            yield LLMProviderEvent(type="token", delta="Hello")
            yield LLMProviderEvent(type="token", delta=" world")

        return LLMProviderStream(iterator=_iterator())

    gateway.register_provider("openai", _factory)

    result = await gateway.run(
        run_id="run",
        trace_id="trace",
        prompt="Hello world",
        params=LLMCallParams(),
        context_hash=None,
        cancel_token=asyncio.Event(),
    )

    assert result["finish_reason"] == "stop_on_budget"
    assert result["error"] == "budget_exhausted"

    events = await _drain_events(queue)
    event_types = [evt["type"] for evt in events]
    assert "llm/budget_exhausted" in event_types
    assert "llm/complete" in event_types
    assert budget_counter.calls


@pytest.mark.anyio("asyncio")
async def test_gateway_handles_cancellation(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = _base_settings()
    state = _FakeState()
    fanout = LLMEventFanout()
    queue = await fanout.subscribe()
    state.llm_streams["run"] = fanout
    state.runs["run"] = {}
    gateway = LLMGateway(settings, state=state, artifact_store=_FakeArtifactStore())
    _register_default_gateway(monkeypatch)

    cancel_flag = asyncio.Event()

    async def _factory(prompt: str, params: LLMCallParams, handle: ProviderHandle, meta: Dict[str, Any]) -> LLMProviderStream:
        async def _iterator():
            for chunk in ("Hello", " world"):
                if cancel_flag.is_set():
                    break
                yield LLMProviderEvent(type="token", delta=chunk)
                await asyncio.sleep(0)
            if not cancel_flag.is_set():
                yield LLMProviderEvent(type="complete", finish_reason="stop")

        async def _cancel():
            cancel_flag.set()

        return LLMProviderStream(iterator=_iterator(), cancel=_cancel)

    gateway.register_provider("openai", _factory)

    cancel_event = asyncio.Event()
    run_task = asyncio.create_task(
        gateway.run(
            run_id="run",
            trace_id="trace",
            prompt="Hello world",
            params=LLMCallParams(),
            context_hash=None,
            cancel_token=cancel_event,
        )
    )

    first_event = json.loads(await queue.get())
    assert first_event["type"] == "llm/provider_selected"
    start_event = json.loads(await queue.get())
    assert start_event["type"] == "llm/starting"
    token_event = json.loads(await queue.get())
    assert token_event["type"] == "llm/token"
    cancel_event.set()

    result = await run_task
    assert result["finish_reason"] == "canceled"
    events = await _drain_events(queue)
    event_types = [evt["type"] for evt in events]
    assert "llm/canceled" in event_types


@pytest.mark.anyio("asyncio")
async def test_gateway_failover_to_secondary_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = Settings(
        openai=OpenAISettings(api_key="sk-openai", default_model="gpt-test"),
        anthropic=AnthropicSettings(api_key="sk-anthropic", default_model="claude-test"),
        llm_gateway=LLMGatewaySettings(
            llm_default_provider="openai",
            llm_default_model="gpt-test",
            llm_retry_max=0,
            llm_retry_base_ms=0,
            llm_retry_jitter_ms=0,
            llm_provider_chain=[
                LLMProviderFallback(provider="openai"),
                LLMProviderFallback(provider="anthropic"),
            ],
        ),
    )

    state = _FakeState()
    fanout = LLMEventFanout()
    queue_primary = await fanout.subscribe()
    queue_secondary = await fanout.subscribe()
    state.llm_streams["run"] = fanout
    state.runs["run"] = {}
    gateway = LLMGateway(settings, state=state, artifact_store=_FakeArtifactStore())
    _, _, fallback_counter, _ = _register_default_gateway(monkeypatch)

    async def _failing_factory(
        prompt: str, params: LLMCallParams, handle: ProviderHandle, meta: Dict[str, Any]
    ) -> LLMProviderStream:
        raise LLMProviderError("primary down", retryable=False, category="provider_unavailable")

    async def _success_factory(
        prompt: str, params: LLMCallParams, handle: ProviderHandle, meta: Dict[str, Any]
    ) -> LLMProviderStream:
        async def _iterator():
            yield LLMProviderEvent(type="token", delta="ok")
            yield LLMProviderEvent(type="complete", finish_reason="stop", usage={"completion_tokens": 1})

        return LLMProviderStream(iterator=_iterator())

    gateway.register_provider("openai", _failing_factory)
    gateway.register_provider("anthropic", _success_factory)

    result = await gateway.run(
        run_id="run",
        trace_id="trace",
        prompt="Hello",
        params=LLMCallParams(),
        context_hash=None,
        cancel_token=asyncio.Event(),
    )

    assert result["provider"] == "anthropic"
    assert len(fallback_counter.calls) == 1
    attributes = fallback_counter.calls[0][1]
    assert attributes["from_provider"] == "openai"
    assert attributes["to_provider"] == "anthropic"

    primary_events = await _drain_events(queue_primary)
    secondary_events = await _drain_events(queue_secondary)
    assert any(evt["type"] == "llm/provider_failover" for evt in primary_events)
    assert any(evt["type"] == "llm/provider_failover" for evt in secondary_events)
    assert any(evt["type"] == "llm/complete" for evt in primary_events)


@pytest.mark.anyio("asyncio")
async def test_llm_event_fanout_multiple_subscribers(monkeypatch: pytest.MonkeyPatch) -> None:
    counter = _Counter()
    monkeypatch.setattr("mcp_agent.llm.events.llm_sse_consumer_count", counter)

    fanout = LLMEventFanout()
    q1 = await fanout.subscribe()
    q2 = await fanout.subscribe()

    await fanout.publish("payload")
    assert await q1.get() == "payload"
    assert await q2.get() == "payload"

    await fanout.unsubscribe(q1)
    await fanout.publish("next")
    assert await q2.get() == "next"
    with pytest.raises(asyncio.QueueEmpty):
        q1.get_nowait()

    await fanout.close()
    assert len(counter.calls) == 4
