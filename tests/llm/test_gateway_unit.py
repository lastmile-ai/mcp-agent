import asyncio
import json
import pathlib
import sys
from typing import Any, Dict

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "src"))

from mcp_agent.config import LLMGatewaySettings, OpenAISettings, Settings
from mcp_agent.llm.gateway import (
    LLMCallParams,
    LLMGateway,
    LLMProviderEvent,
    LLMProviderStream,
    LLMCapExceededError,
    RetryableLLMProviderError,
)
from mcp_agent.workflows.llm.llm_selector import ProviderHandle


class _FakeState:
    def __init__(self) -> None:
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


def _register_default_gateway(monkeypatch: pytest.MonkeyPatch) -> tuple[_Counter, _Counter]:
    tokens_counter = _Counter()
    failures_counter = _Counter()
    monkeypatch.setattr("mcp_agent.telemetry.llm_tokens_total", tokens_counter)
    monkeypatch.setattr("mcp_agent.telemetry.llm_failures_total", failures_counter)
    monkeypatch.setattr("mcp_agent.llm.gateway.llm_tokens_total", tokens_counter)
    monkeypatch.setattr("mcp_agent.llm.gateway.llm_failures_total", failures_counter)
    return tokens_counter, failures_counter


@pytest.mark.anyio("asyncio")
async def test_gateway_stream_success(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = _base_settings()
    state = _FakeState()
    queue: asyncio.Queue[str] = asyncio.Queue()
    state.queues["run"] = {queue}
    state.runs["run"] = {}
    store = _FakeArtifactStore()
    gateway = LLMGateway(settings, state=state, artifact_store=store)
    tokens_counter, failures_counter = _register_default_gateway(monkeypatch)

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

    monkeypatch.setattr(
        "mcp_agent.llm.gateway.select_llm_provider",
        lambda model_hint, cfg: ProviderHandle(provider="openai", model="gpt-test"),
    )
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
    assert event_types[:2] == ["llm/starting", "llm/token"]
    assert event_types[-1] == "llm/complete"

    assert store.saved, "request snapshot should be persisted"
    saved_json = json.loads(store.saved[0][2].decode("utf-8"))
    assert saved_json["prompt_hash"].startswith("sha256:")


@pytest.mark.anyio("asyncio")
async def test_gateway_retries_transient_error(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = _base_settings()
    state = _FakeState()
    queue: asyncio.Queue[str] = asyncio.Queue()
    state.queues["run"] = {queue}
    state.runs["run"] = {}
    gateway = LLMGateway(settings, state=state, artifact_store=_FakeArtifactStore())
    _register_default_gateway(monkeypatch)

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
    queue: asyncio.Queue[str] = asyncio.Queue()
    state.queues["run"] = {queue}
    state.runs["run"] = {}
    gateway = LLMGateway(settings, state=state, artifact_store=_FakeArtifactStore())
    _register_default_gateway(monkeypatch)

    async def _factory(prompt: str, params: LLMCallParams, handle: ProviderHandle, meta: Dict[str, Any]) -> LLMProviderStream:
        async def _iterator():
            yield LLMProviderEvent(type="token", delta="Hello")
            yield LLMProviderEvent(type="token", delta=" world")

        return LLMProviderStream(iterator=_iterator())

    gateway.register_provider("openai", _factory)

    with pytest.raises(LLMCapExceededError):
        await gateway.run(
            run_id="run",
            trace_id="trace",
            prompt="Hello world",
            params=LLMCallParams(),
            context_hash=None,
            cancel_token=asyncio.Event(),
        )

    events = await _drain_events(queue)
    assert any(evt["type"] == "llm/canceled" for evt in events)
    assert any(evt["type"] == "llm/error" and evt.get("violation") for evt in events)


@pytest.mark.anyio("asyncio")
async def test_gateway_handles_cancellation(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = _base_settings()
    state = _FakeState()
    queue: asyncio.Queue[str] = asyncio.Queue()
    state.queues["run"] = {queue}
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

    start_event = json.loads(await queue.get())
    assert start_event["type"] == "llm/starting"
    token_event = json.loads(await queue.get())
    assert token_event["type"] == "llm/token"
    cancel_event.set()

    result = await run_task
    assert result["finish_reason"] == "canceled"
    events = await _drain_events(queue)
    assert events[-1]["type"] == "llm/canceled"
