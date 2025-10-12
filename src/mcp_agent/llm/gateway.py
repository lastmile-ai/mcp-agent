"""Unified gateway for invoking LLM providers with streaming, persistence, and telemetry."""

from __future__ import annotations

import asyncio
import hashlib
import json
import random
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import (
    Any,
    AsyncIterator,
    Awaitable,
    Callable,
    Dict,
    Mapping,
    MutableMapping,
    Sequence,
    Optional,
    Protocol,
)

from pydantic import BaseModel, Field
from opentelemetry import trace
from opentelemetry.trace import Status, StatusCode, set_span_in_context

from mcp_agent.config import LLMGatewaySettings, Settings
from mcp_agent.llm.events import emit_llm_event
from mcp_agent.telemetry import (
    llm_budget_abort_total,
    llm_failures_total,
    llm_provider_fallback_total,
    llm_tokens_total,
)
from mcp_agent.workflows.llm.llm_selector import (
    ProviderHandle,
    select_llm_provider_chain,
)


class ArtifactStore(Protocol):
    async def put(
        self,
        run_id: str,
        path: str,
        data: bytes,
        content_type: str = "application/json",
    ) -> str:
        ...


class LLMCallParams(BaseModel):
    """Runtime parameters describing an LLM invocation."""

    provider: Optional[str] = None
    model: Optional[str] = None
    temperature: Optional[float] = None
    top_p: Optional[float] = None
    max_tokens: Optional[int] = None
    extra: Dict[str, Any] = Field(default_factory=dict)


class LLMProviderEvent(BaseModel):
    """Event yielded by provider streams."""

    type: str = "token"
    delta: str | None = None
    finish_reason: str | None = None
    retryable: bool | None = None
    category: str | None = None
    violation: bool | None = None
    usage: Dict[str, Any] | None = None
    error: str | None = None


@dataclass
class LLMProviderStream:
    """Wrapper around an async iterator of provider events."""

    iterator: AsyncIterator[LLMProviderEvent]
    cancel: Callable[[], Awaitable[None]] | None = None
    usage: Dict[str, Any] = field(default_factory=dict)


ProviderFactory = Callable[
    [str, LLMCallParams, ProviderHandle, Dict[str, Any]],
    Awaitable[LLMProviderStream],
]


class LLMProviderError(Exception):
    """Base exception raised when providers fail."""

    def __init__(self, message: str, *, retryable: bool = False, category: str = "unknown", violation: bool = False):
        super().__init__(message)
        self.retryable = retryable
        self.category = category
        self.violation = violation


class RetryableLLMProviderError(LLMProviderError):
    """Exception describing retryable provider failures."""

    def __init__(self, message: str, category: str = "transient"):
        super().__init__(message, retryable=True, category=category)


class LLMCapExceededError(LLMProviderError):
    """Raised when configured caps are exceeded."""

    def __init__(self, message: str, category: str = "cap_exceeded"):
        super().__init__(message, retryable=False, category=category, violation=True)


class AllProvidersExhausted(LLMProviderError):
    """Raised when the provider chain has no remaining fallbacks."""

    def __init__(self, message: str, *, attempted: Sequence[str]):
        super().__init__(message, retryable=False, category="provider_exhausted")
        self.attempted = list(attempted)


LOGGER = logging.getLogger("mcp_agent.llm.gateway")

FAILOVER_CATEGORIES: set[str] = {
    "provider_error",
    "provider_unavailable",
    "quota_exceeded",
    "rate_limit",
    "timeout",
    "server_error",
    "transient",
    "api_error",
}


class _StateArtifactStore:
    """Adapter writing artifacts into the in-memory state store used by public API tests."""

    def __init__(self, state: Any) -> None:
        self._state = state
        if not hasattr(self._state, "artifacts"):
            self._state.artifacts = {}  # type: ignore[attr-defined]

    async def put(self, run_id: str, path: str, data: bytes, content_type: str = "application/json") -> str:
        aid = f"{run_id}:{path}"
        self._state.artifacts[aid] = (data, content_type)
        return f"mem://{aid}"


def _is_secret_key(key: str) -> bool:
    lowered = key.lower()
    return any(token in lowered for token in ("key", "secret", "token", "password"))


def _redact(value: Any) -> Any:
    if isinstance(value, MutableMapping):
        return {k: ("***" if _is_secret_key(k) else _redact(v)) for k, v in value.items()}
    if isinstance(value, list):
        return [_redact(v) for v in value]
    return value


def _hash_json(payload: Dict[str, Any]) -> str:
    return "sha256:" + hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()


def _hash_text(text: str | None) -> str | None:
    if not text:
        return None
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


class LLMGateway:
    """Co-ordinates provider selection, persistence, SSE emission, and retries."""

    def __init__(
        self,
        settings: Settings,
        *,
        state: Any | None = None,
        artifact_store: ArtifactStore | None = None,
        providers: Mapping[str, ProviderFactory] | None = None,
        sleep: Callable[[float], Awaitable[None]] | None = None,
        on_active_window: Callable[[str, str, str], None] | None = None,
    ) -> None:
        self._settings = settings
        self._state = state
        if artifact_store is None and state is not None:
            artifact_store = _StateArtifactStore(state)
        self._artifact_store = artifact_store
        self._providers: Dict[str, ProviderFactory] = {k.lower(): v for k, v in (providers or {}).items()}
        self._sleep = sleep or asyncio.sleep
        self._random = random.Random()
        self._transient_seq = 0
        self._tracer = trace.get_tracer("mcp-agent.llm")
        self._active_window_hook = on_active_window

    def register_provider(self, name: str, factory: ProviderFactory) -> None:
        """Register a provider factory accessible via :class:`ProviderHandle` identifiers."""

        self._providers[name.lower()] = factory

    async def run(
        self,
        run_id: str,
        trace_id: str,
        prompt: str,
        params: LLMCallParams,
        context_hash: str | None,
        cancel_token: asyncio.Event,
    ) -> Dict[str, Any]:
        """Execute an LLM call and stream events back through SSE queues.

        Returns a summary dictionary with token usage, finish reason, and error information.
        Raises :class:`LLMProviderError` when all retry attempts fail.
        """

        active_hook = self._active_window_hook
        if active_hook:
            active_hook(run_id, trace_id, "start")

        cfg = self._settings.llm_gateway or LLMGatewaySettings()
        provider_hint = None
        if params.provider and params.model:
            provider_hint = f"{params.provider}:{params.model}"
        elif params.provider:
            provider_hint = params.provider
        else:
            provider_hint = params.model

        provider_chain = select_llm_provider_chain(provider_hint, self._settings)
        if not provider_chain:
            raise ValueError("No LLM providers are configured")

        prompt_hash = _hash_text(prompt) or "sha256:" + hashlib.sha256(b"").hexdigest()
        tracer_span = self._tracer.start_span("llm.call")
        tracer_span.set_attribute("run_id", run_id)
        tracer_span.set_attribute("trace_id", trace_id)
        tracer_span.set_attribute("llm.provider_chain_length", len(provider_chain))
        tracer_span.set_attribute(
            "llm.provider_chain",
            ",".join(
                f"{candidate.provider}:{candidate.model}" if candidate.model else candidate.provider
                for candidate in provider_chain
            ),
        )

        attempted_labels: list[str] = []
        last_error: LLMProviderError | None = None

        try:
            for chain_index, handle in enumerate(provider_chain):
                model_name = params.model or handle.model
                effective_params = params.model_copy(
                    update={"provider": handle.provider, "model": model_name}
                )
                redacted_params = _redact(
                    effective_params.model_dump(exclude_none=True, by_alias=True)
                )
                params_hash = _hash_json(redacted_params)
                instructions_source = None
                extra_payload = effective_params.extra or {}
                for key in ("system", "system_prompt", "instructions"):
                    if isinstance(extra_payload.get(key), str):
                        instructions_source = extra_payload[key]
                        break
                instructions_hash = _hash_text(instructions_source)

                seq = self._next_call_seq(run_id)
                await self._persist_request(
                    run_id=run_id,
                    provider=handle.provider,
                    model=model_name,
                    params_payload=redacted_params,
                    prompt_hash=prompt_hash,
                    instructions_hash=instructions_hash,
                    context_hash=context_hash,
                    sequence=seq,
                    trace_id=trace_id,
                )

                provider_label = (
                    f"{handle.provider}:{model_name}" if model_name else handle.provider
                )
                await emit_llm_event(
                    self._state,
                    run_id,
                    "llm/provider_selected",
                    {
                        "provider": handle.provider,
                        "model": model_name,
                        "params_hash": params_hash,
                        "prompt_hash": prompt_hash,
                        "instructions_hash": instructions_hash,
                        "chain_index": chain_index,
                        "chain_length": len(provider_chain),
                    },
                )
                LOGGER.info(
                    "Selected LLM provider",
                    extra={
                        "run_id": run_id,
                        "trace_id": trace_id,
                        "provider": handle.provider,
                        "model": model_name,
                        "chain_index": chain_index,
                    },
                )

                provider_key = handle.provider.lower()
                provider_span = self._tracer.start_span(
                    "llm.provider",
                    context=set_span_in_context(tracer_span),
                )
                provider_span.set_attribute("llm.provider", handle.provider)
                provider_span.set_attribute("llm.provider.index", chain_index)
                if model_name:
                    provider_span.set_attribute("llm.model", model_name)

                attempt = 0
                try:
                    while True:
                        attempt += 1
                        try:
                            payload = await self._run_attempt(
                                run_id=run_id,
                                trace_id=trace_id,
                                prompt=prompt,
                                params=effective_params,
                                handle=handle,
                                provider_key=provider_key,
                                params_hash=params_hash,
                                prompt_hash=prompt_hash,
                                instructions_hash=instructions_hash,
                                cancel_token=cancel_token,
                                cfg=cfg,
                                attempt=attempt,
                                span=provider_span,
                                chain_index=chain_index,
                                chain_length=len(provider_chain),
                            )
                            tracer_span.set_attribute("llm.provider", handle.provider)
                            if model_name:
                                tracer_span.set_attribute("llm.model", model_name)
                            provider_span.set_status(Status(StatusCode.OK))
                            await emit_llm_event(
                                self._state,
                                run_id,
                                "llm/provider_succeeded",
                                {
                                    "provider": handle.provider,
                                    "model": model_name,
                                    "attempt": attempt,
                                    "chain_index": chain_index,
                                },
                            )
                            LOGGER.info(
                                "LLM provider succeeded",
                                extra={
                                    "run_id": run_id,
                                    "trace_id": trace_id,
                                    "provider": handle.provider,
                                    "model": model_name,
                                    "attempt": attempt,
                                },
                            )
                            return payload
                        except LLMProviderError as exc:
                            last_error = exc
                            attempted_labels.append(provider_label)
                            await self._record_failure(
                                run_id=run_id,
                                handle=handle,
                                model_name=model_name,
                                attempt=attempt,
                                chain_index=chain_index,
                                error=exc,
                            )
                            tracer_span.record_exception(exc)
                            provider_span.record_exception(exc)
                            if self._should_retry(exc, attempt, cfg):
                                await self._sleep(self._compute_backoff(attempt - 1, cfg))
                                continue
                            provider_span.set_status(Status(StatusCode.ERROR))
                            if (
                                self._should_failover(exc)
                                and chain_index + 1 < len(provider_chain)
                            ):
                                next_handle = provider_chain[chain_index + 1]
                                await self._emit_failover(
                                    run_id=run_id,
                                    current=handle,
                                    next_handle=next_handle,
                                    model_name=model_name,
                                    attempt=attempt,
                                    error=exc,
                                    chain_index=chain_index,
                                )
                                llm_provider_fallback_total.add(
                                    1,
                                    {
                                        "from_provider": handle.provider,
                                        "to_provider": next_handle.provider,
                                    },
                                )
                                LOGGER.warning(
                                    "Failing over to next LLM provider",
                                    extra={
                                        "run_id": run_id,
                                        "trace_id": trace_id,
                                        "from_provider": handle.provider,
                                        "to_provider": next_handle.provider,
                                        "error_category": exc.category,
                                    },
                                )
                                break
                            tracer_span.set_status(Status(StatusCode.ERROR))
                            LOGGER.error(
                                "LLM provider failed with no remaining fallback",
                                extra={
                                    "run_id": run_id,
                                    "trace_id": trace_id,
                                    "provider": handle.provider,
                                    "error": str(exc),
                                    "category": exc.category,
                                },
                            )
                            raise
                finally:
                    provider_span.end()

            if last_error is not None:
                tracer_span.set_status(Status(StatusCode.ERROR))
                raise AllProvidersExhausted(
                    "All configured LLM providers failed",
                    attempted=attempted_labels
                    or [
                        f"{candidate.provider}:{candidate.model}"
                        if candidate.model
                        else candidate.provider
                        for candidate in provider_chain
                    ],
                ) from last_error
            tracer_span.set_status(Status(StatusCode.ERROR))
            raise AllProvidersExhausted(
                "No LLM providers remained after failover attempts",
                attempted=[
                    f"{candidate.provider}:{candidate.model}"
                    if candidate.model
                    else candidate.provider
                    for candidate in provider_chain
                ],
            )
        finally:
            tracer_span.end()
            if active_hook:
                active_hook(run_id, trace_id, "stop")

    async def _record_failure(
        self,
        *,
        run_id: str,
        handle: ProviderHandle,
        model_name: str | None,
        attempt: int,
        chain_index: int,
        error: LLMProviderError,
    ) -> None:
        await emit_llm_event(
            self._state,
            run_id,
            "llm/error",
            {
                "category": error.category,
                "message": str(error),
                "retryable": error.retryable,
                "attempt": attempt,
                "violation": bool(error.violation),
            },
        )
        await emit_llm_event(
            self._state,
            run_id,
            "llm/provider_failed",
            {
                "provider": handle.provider,
                "model": model_name,
                "attempt": attempt,
                "chain_index": chain_index,
                "category": error.category,
                "violation": bool(error.violation),
            },
        )
        llm_failures_total.add(
            1,
            {
                "provider": handle.provider,
                "model": model_name or "",
                "category": error.category,
            },
        )

    async def _emit_failover(
        self,
        *,
        run_id: str,
        current: ProviderHandle,
        next_handle: ProviderHandle,
        model_name: str | None,
        attempt: int,
        error: LLMProviderError,
        chain_index: int,
    ) -> None:
        await emit_llm_event(
            self._state,
            run_id,
            "llm/provider_failover",
            {
                "from_provider": current.provider,
                "from_model": model_name,
                "to_provider": next_handle.provider,
                "to_model": next_handle.model,
                "attempt": attempt,
                "chain_index": chain_index,
                "category": error.category,
            },
        )

    @staticmethod
    def _should_retry(error: LLMProviderError, attempt: int, cfg: LLMGatewaySettings) -> bool:
        return error.retryable and attempt <= cfg.llm_retry_max

    @staticmethod
    def _should_failover(error: LLMProviderError) -> bool:
        if error.violation:
            return False
        if error.category in {"cap_exceeded", "budget_exhausted"}:
            return False
        return error.retryable or error.category in FAILOVER_CATEGORIES

    async def _handle_budget_abort(
        self,
        *,
        run_id: str,
        stream: LLMProviderStream,
        handle: ProviderHandle,
        model_name: str | None,
        reason: str,
        attempt: int,
        chain_index: int,
        prompt_tokens: int,
        completion_tokens: int,
        cost_usd: float,
        span,
    ) -> None:
        await self._cancel_stream(stream)
        await emit_llm_event(
            self._state,
            run_id,
            "llm/error",
            {
                "category": "budget_exhausted",
                "message": f"{reason} exceeded",
                "retryable": False,
                "attempt": attempt,
                "violation": False,
            },
        )
        await emit_llm_event(
            self._state,
            run_id,
            "llm/budget_exhausted",
            {
                "provider": handle.provider,
                "model": model_name,
                "reason": reason,
                "chain_index": chain_index,
                "tokens_prompt": prompt_tokens,
                "tokens_completion": completion_tokens,
                "cost_usd": cost_usd,
            },
        )
        llm_budget_abort_total.add(
            1,
            {"provider": handle.provider, "model": model_name or "", "reason": reason},
        )
        span.add_event(
            "llm.budget_exhausted",
            {
                "reason": reason,
                "tokens_completion": completion_tokens,
                "cost_usd": cost_usd,
            },
        )

    async def _run_attempt(
        self,
        *,
        run_id: str,
        trace_id: str,
        prompt: str,
        params: LLMCallParams,
        handle: ProviderHandle,
        provider_key: str,
        params_hash: str,
        prompt_hash: str,
        instructions_hash: str | None,
        cancel_token: asyncio.Event,
        cfg: LLMGatewaySettings,
        attempt: int,
        span,
        chain_index: int,
        chain_length: int,
    ) -> Dict[str, Any]:
        model_name = params.model
        await emit_llm_event(
            self._state,
            run_id,
            "llm/starting",
            {
                "provider": handle.provider,
                "model": model_name,
                "params_hash": params_hash,
                "prompt_hash": prompt_hash,
                "instructions_hash": instructions_hash,
                "violation": False,
                "attempt": attempt,
                "chain_index": chain_index,
                "chain_length": chain_length,
            },
        )

        factory = self._providers.get(provider_key)
        if factory is None:
            raise LLMProviderError(
                f"No registered provider factory for '{handle.provider}'",
                category="provider_unavailable",
            )

        try:
            stream = await factory(
                prompt,
                params,
                handle,
                {"run_id": run_id, "trace_id": trace_id, "attempt": attempt},
            )
        except LLMProviderError:
            raise
        except Exception as exc:  # pragma: no cover - defensive
            raise LLMProviderError(str(exc), category="provider_error") from exc

        prompt_tokens = int(stream.usage.get("prompt_tokens", 0) or 0)
        if not prompt_tokens:
            prompt_tokens = self._estimate_prompt_tokens(prompt)
        if prompt_tokens:
            llm_tokens_total.add(
                prompt_tokens,
                {"provider": handle.provider, "model": model_name or "", "kind": "prompt"},
            )
        span.set_attribute("llm.prompt_tokens", prompt_tokens)

        completion_tokens = int(stream.usage.get("completion_tokens", 0) or 0)
        cost_usd = float(stream.usage.get("cost_usd", 0) or 0)
        finish_reason: str | None = None

        token_cap = cfg.llm_tokens_cap
        if params.max_tokens is not None:
            token_cap = min(token_cap, params.max_tokens) if token_cap is not None else params.max_tokens
        cost_cap = cfg.llm_cost_cap_usd

        idx = 0
        last_error: Exception | None = None

        async for event in stream.iterator:
            if cancel_token.is_set():
                await self._cancel_stream(stream)
                await emit_llm_event(
                    self._state,
                    run_id,
                    "llm/canceled",
                    {"reason": "cancel_token"},
                )
                span.set_attribute("llm.finish_reason", "canceled")
                return {
                    "provider": handle.provider,
                    "model": model_name,
                    "tokens_prompt": prompt_tokens,
                    "tokens_completion": completion_tokens,
                    "finish_reason": "canceled",
                    "error": None,
                }

            event_type = event.type or "token"
            if event_type == "token":
                delta = event.delta or ""
                await emit_llm_event(
                    self._state,
                    run_id,
                    "llm/token",
                    {"delta": delta, "idx": idx},
                )
                idx += 1
                inc = self._estimate_tokens(delta)
                if inc:
                    completion_tokens += inc
                    llm_tokens_total.add(
                        inc,
                        {
                            "provider": handle.provider,
                            "model": model_name or "",
                            "kind": "completion",
                        },
                    )
                usage = event.usage or {}
                if "cost_usd" in usage:
                    cost_usd = float(usage["cost_usd"])
                if token_cap is not None and completion_tokens >= token_cap:
                    completion_tokens = token_cap
                    finish_reason = "stop_on_budget"
                    await self._handle_budget_abort(
                        run_id=run_id,
                        stream=stream,
                        handle=handle,
                        model_name=model_name,
                        reason="token_cap",
                        attempt=attempt,
                        chain_index=chain_index,
                        prompt_tokens=prompt_tokens,
                        completion_tokens=completion_tokens,
                        cost_usd=cost_usd,
                        span=span,
                    )
                    break
                if cost_cap is not None and cost_usd >= cost_cap:
                    finish_reason = "stop_on_budget"
                    await self._handle_budget_abort(
                        run_id=run_id,
                        stream=stream,
                        handle=handle,
                        model_name=model_name,
                        reason="cost_cap",
                        attempt=attempt,
                        chain_index=chain_index,
                        prompt_tokens=prompt_tokens,
                        completion_tokens=completion_tokens,
                        cost_usd=cost_usd,
                        span=span,
                    )
                    break
            elif event_type == "complete":
                finish_reason = event.finish_reason or finish_reason or "stop"
                usage = event.usage or {}
                if "completion_tokens" in usage:
                    completion_tokens = int(usage["completion_tokens"])
                if "prompt_tokens" in usage:
                    prompt_tokens = int(usage["prompt_tokens"])
                if "cost_usd" in usage:
                    cost_usd = float(usage["cost_usd"])
            elif event_type == "error":
                last_error = LLMProviderError(
                    event.error or "provider_error",
                    retryable=bool(event.retryable),
                    category=event.category or "provider_error",
                    violation=bool(event.violation),
                )
                break

        if last_error:
            raise last_error

        finish_reason = finish_reason or "stop"
        span.set_attribute("llm.finish_reason", finish_reason)
        span.set_attribute("llm.completion_tokens", completion_tokens)
        span.set_attribute("llm.cost_usd", cost_usd)

        payload = {
            "provider": handle.provider,
            "model": model_name,
            "tokens_prompt": prompt_tokens,
            "tokens_completion": completion_tokens,
            "finish_reason": finish_reason,
            "error": None,
        }
        complete_payload = {
            "finish_reason": finish_reason,
            "tokens_prompt": prompt_tokens,
            "tokens_completion": completion_tokens,
        }
        if finish_reason == "stop_on_budget":
            payload["error"] = "budget_exhausted"
            complete_payload["budget_exhausted"] = True
        if cost_usd:
            complete_payload["cost_usd"] = cost_usd
            payload["cost_usd"] = cost_usd

        await emit_llm_event(
            self._state,
            run_id,
            "llm/complete",
            complete_payload,
        )

        return payload

    async def _persist_request(
        self,
        *,
        run_id: str,
        provider: str,
        model: str | None,
        params_payload: Dict[str, Any],
        prompt_hash: str,
        instructions_hash: str | None,
        context_hash: str | None,
        sequence: int,
        trace_id: str,
    ) -> None:
        if self._artifact_store is None:
            return
        artifact_path = f"artifacts/llm/{run_id}/{sequence:04d}/request.json"
        payload = {
            "trace_id": trace_id,
            "run_id": run_id,
            "provider": provider,
            "model": model,
            "params": params_payload,
            "prompt_hash": prompt_hash,
            "instructions_hash": instructions_hash,
            "context_hash": context_hash,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        data = json.dumps(payload, indent=2).encode("utf-8")
        await self._artifact_store.put(run_id, artifact_path, data, content_type="application/json")

    async def _cancel_stream(self, stream: LLMProviderStream) -> None:
        cancel = stream.cancel
        if cancel is None:
            return
        try:
            result = cancel()
            if asyncio.iscoroutine(result):
                await result
        except Exception:
            pass

    def _next_call_seq(self, run_id: str) -> int:
        if self._state and hasattr(self._state, "runs"):
            runs = getattr(self._state, "runs")
            run_state = runs.setdefault(run_id, {})
            seq = int(run_state.get("_llm_seq", 0)) + 1
            run_state["_llm_seq"] = seq
            return seq
        self._transient_seq += 1
        return self._transient_seq

    def _compute_backoff(self, attempt_index: int, cfg: LLMGatewaySettings) -> float:
        base = max(cfg.llm_retry_base_ms, 0) / 1000.0
        jitter_max = max(cfg.llm_retry_jitter_ms, 0) / 1000.0
        jitter = self._random.uniform(0, jitter_max) if jitter_max else 0.0
        return base * (2**attempt_index) + jitter

    @staticmethod
    def _estimate_tokens(text: str) -> int:
        stripped = text.strip()
        if not stripped:
            return 0
        return max(1, len(stripped.split()))

    @staticmethod
    def _estimate_prompt_tokens(prompt: str) -> int:
        stripped = prompt.strip()
        if not stripped:
            return 0
        return max(1, len(stripped.split()))
