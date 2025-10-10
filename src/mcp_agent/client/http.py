"""Resilient async HTTP client with retries, breakers, and telemetry."""

from __future__ import annotations

import asyncio
import json
import os
import random
import time
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any, Awaitable, Callable, Dict, Iterable, Optional, Tuple
from urllib.parse import urljoin, urlparse

import httpx
from opentelemetry import metrics, trace
from opentelemetry.metrics import Observation
from opentelemetry.trace import SpanKind, Status, StatusCode

from ..errors.canonical import CircuitOpenError, map_httpx_error

_logger = __import__("logging").getLogger(__name__)
_tracer = trace.get_tracer("mcp_agent.client.http")
_meter = metrics.get_meter("mcp_agent.client.http")

_http_client_latency = _meter.create_histogram(
    "http_client_latency_ms",
    unit="ms",
    description="Total latency of MCP tool HTTP calls",
)
_http_client_retries = _meter.create_counter(
    "http_client_retries_total",
    description="Retry attempts performed by the MCP HTTP client",
)
_tool_errors_total = _meter.create_counter(
    "tool_client_errors_total",
    description="Canonical tool errors emitted by the MCP HTTP client",
)


@dataclass(slots=True)
class HTTPClientConfig:
    read_timeout_ms: int = int(os.getenv("HTTP_TIMEOUT_MS", "1500"))
    connect_timeout_ms: int = int(os.getenv("HTTP_CONNECT_TIMEOUT_MS", "500"))
    write_timeout_ms: int = int(os.getenv("HTTP_WRITE_TIMEOUT_MS", "1500"))
    pool_timeout_ms: int = int(os.getenv("HTTP_POOL_TIMEOUT_MS", "500"))
    retry_max: int = int(os.getenv("RETRY_MAX", "3"))
    retry_base_ms: int = int(os.getenv("RETRY_BASE_MS", "100"))
    retry_jitter: float = float(os.getenv("RETRY_JITTER", "0.2"))
    breaker_enabled: bool = os.getenv("BREAKER_ENABLED", "false").lower() in {"1", "true", "yes"}
    breaker_threshold: float = float(os.getenv("BREAKER_THRESH", "0.5"))
    breaker_window: int = int(os.getenv("BREAKER_WINDOW", "20"))
    breaker_cooldown_ms: int = int(os.getenv("BREAKER_COOLDOWN_MS", "5000"))
    half_open_max: int = int(os.getenv("HALF_OPEN_MAX", "3"))
    allowed_hosts: Tuple[str, ...] = tuple(
        host.strip()
        for host in os.getenv("ALLOWED_HOSTS", "").split(",")
        if host.strip()
    )

    def build_timeout(self) -> httpx.Timeout:
        return httpx.Timeout(
            connect=self.connect_timeout_ms / 1000.0,
            read=self.read_timeout_ms / 1000.0,
            write=self.write_timeout_ms / 1000.0,
            pool=self.pool_timeout_ms / 1000.0,
        )


class CircuitBreaker:
    """Rolling error-rate circuit breaker."""

    def __init__(
        self,
        config: HTTPClientConfig,
        *,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._config = config
        self._clock = clock
        self._state = "closed"
        self._open_until = 0.0
        self._half_open_attempts = 0
        self._window: deque[bool] = deque(maxlen=max(1, config.breaker_window))

    @property
    def state(self) -> str:
        return self._state

    def allow_request(self) -> Tuple[bool, str]:
        now = self._clock()
        if self._state == "open":
            if now >= self._open_until:
                self._transition("half_open")
            else:
                return False, "open"
        if self._state == "half_open":
            if self._half_open_attempts >= self._config.half_open_max:
                return False, "half_open"
            self._half_open_attempts += 1
            return True, "half_open"
        return True, self._state

    def record_success(self) -> Tuple[str, bool]:
        previous = self._state
        self._window.append(True)
        if self._state in {"open", "half_open"}:
            self._transition("closed")
        self._half_open_attempts = 0
        return self._state, self._state != previous

    def record_failure(self) -> Tuple[str, bool]:
        previous = self._state
        now = self._clock()
        self._window.append(False)
        if self._state == "half_open":
            self._trip(now)
        elif len(self._window) == self._window.maxlen:
            failures = self._window.count(False)
            error_rate = failures / len(self._window)
            if error_rate >= self._config.breaker_threshold:
                self._trip(now)
        return self._state, self._state != previous

    def _transition(self, state: str) -> None:
        self._state = state
        if state == "closed":
            self._open_until = 0.0
            self._half_open_attempts = 0
            self._window.clear()

    def _trip(self, now: float) -> None:
        self._transition("open")
        self._open_until = now + self._config.breaker_cooldown_ms / 1000.0
        self._half_open_attempts = 0


class _CircuitBreakerRegistry:
    def __init__(self) -> None:
        self._breakers: Dict[str, CircuitBreaker] = {}

    def get(
        self,
        tool: str,
        config: HTTPClientConfig,
        clock: Callable[[], float],
    ) -> CircuitBreaker:
        breaker = self._breakers.get(tool)
        if breaker is None:
            breaker = CircuitBreaker(config, clock=clock)
            self._breakers[tool] = breaker
        return breaker

    def observations(self) -> Iterable[Observation]:
        for tool, breaker in self._breakers.items():
            value = 1 if breaker.state == "open" else 0
            yield Observation(value, {"tool": tool})


_breaker_registry = _CircuitBreakerRegistry()
_meter.create_observable_gauge(
    "http_client_circuit_open",
    callbacks=[lambda _: _breaker_registry.observations()],
    description="Current circuit breaker state for MCP tools",
)

_shared_client: Optional[httpx.AsyncClient] = None


def _build_shared_client(config: HTTPClientConfig) -> httpx.AsyncClient:
    limits = httpx.Limits(max_keepalive_connections=20, max_connections=200)
    return httpx.AsyncClient(
        timeout=config.build_timeout(),
        limits=limits,
        max_redirects=3,
    )


def get_shared_async_client(config: Optional[HTTPClientConfig] = None) -> httpx.AsyncClient:
    global _shared_client
    if _shared_client is None:
        cfg = config or HTTPClientConfig()
        _shared_client = _build_shared_client(cfg)
    return _shared_client


def _redact_headers(headers: Optional[Dict[str, str]]) -> Dict[str, str]:
    if not headers:
        return {}
    redacted: Dict[str, str] = {}
    for key, value in headers.items():
        if key.lower() in {"authorization", "x-signature"} or key.lower().endswith("key"):
            redacted[key] = "<redacted>"
        else:
            redacted[key] = value
    return redacted


def _round(value: float) -> float:
    return round(value, 6)


def _status_class(status_code: int) -> str:
    return f"{status_code // 100}xx"


def _parse_retry_after(value: str) -> Optional[float]:
    try:
        seconds = int(value)
        return float(max(seconds, 0))
    except ValueError:
        try:
            dt = parsedate_to_datetime(value)
        except (TypeError, ValueError):
            return None
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        now = datetime.now(tz=timezone.utc)
        delay = (dt - now).total_seconds()
        return max(delay, 0.0)


class HTTPToolClient:
    """Resilient HTTP client used by tool adapters."""

    def __init__(
        self,
        tool_id: str,
        base_url: str,
        *,
        client: Optional[httpx.AsyncClient] = None,
        config: Optional[HTTPClientConfig] = None,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        rng: Optional["random.Random"] = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        import random

        self.tool_id = tool_id
        self._config = config or HTTPClientConfig()
        self._client = client or get_shared_async_client(self._config)
        self._sleep = sleep
        self._rng = rng or random.Random()
        self._base_url, self._host = self._validate_base_url(base_url)
        self._timeout = self._config.build_timeout()
        self._breaker = (
            _breaker_registry.get(tool_id, self._config, clock)
            if self._config.breaker_enabled
            else None
        )

    def _validate_base_url(self, base_url: str) -> Tuple[str, str]:
        parsed = urlparse(base_url)
        if parsed.scheme not in {"http", "https"}:
            raise ValueError("base_url must use http or https scheme")
        if not parsed.netloc:
            raise ValueError("base_url must be absolute")
        host = parsed.hostname
        if self._config.allowed_hosts and host not in self._config.allowed_hosts:
            raise ValueError(f"host {host} not in allowed hosts")
        return base_url.rstrip("/"), host or ""

    def _build_url(self, path: str) -> str:
        base = self._base_url + ("/" if not self._base_url.endswith("/") else "")
        url = urljoin(base, path.lstrip("/"))
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"}:
            raise ValueError("only http(s) URLs are supported")
        if parsed.netloc != urlparse(self._base_url).netloc:
            raise ValueError("redirects to different host are not allowed")
        return url

    def _jitter_delay(self, attempt: int) -> float:
        base = self._config.retry_base_ms * (2 ** max(0, attempt - 1))
        factor_min = 1 - self._config.retry_jitter
        factor_max = 1 + self._config.retry_jitter
        factor = self._rng.uniform(factor_min, factor_max)
        return max(base * factor, 0.0) / 1000.0

    async def request(
        self,
        method: str,
        path: str,
        *,
        headers: Optional[Dict[str, str]] = None,
        idempotent: Optional[bool] = None,
        **kwargs: Any,
    ) -> httpx.Response:
        method_upper = method.upper()
        url = self._build_url(path)
        headers = headers or {}
        redacted_headers = _redact_headers(headers)
        overall_start = time.perf_counter()
        status_class = "error"
        breaker_state = self._breaker.state if self._breaker else "disabled"
        span_attributes: Dict[str, Any] = {
            "tool": self.tool_id,
            "http.method": method_upper,
            "http.url": url,
        }
        retry_count = 0
        last_exception: Optional[Exception] = None
        response: Optional[httpx.Response] = None
        is_idempotent = (
            method_upper in {"GET", "HEAD", "OPTIONS"}
            if idempotent is None
            else idempotent
        )
        if method_upper == "POST" and not headers.get("Idempotency-Key"):
            is_idempotent = idempotent if idempotent is not None else False
        with _tracer.start_as_current_span("tool.http", kind=SpanKind.CLIENT) as span:
            span.set_attributes(span_attributes)
            while True:
                attempt_number = retry_count + 1
                allowed = True
                if self._breaker:
                    allowed, breaker_state = self._breaker.allow_request()
                    if not allowed:
                        span.add_event("breaker.open", {"tool": self.tool_id})
                        _log_json(
                            phase="breaker",
                            tool=self.tool_id,
                            breaker_state=self._breaker.state,
                            method=method_upper,
                            url=url,
                        )
                        error = CircuitOpenError(self.tool_id)
                        _tool_errors_total.add(1, {"tool": self.tool_id, "code": error.code})
                        span.set_status(Status(StatusCode.ERROR, error.code))
                        span.set_attribute("breaker_state", self._breaker.state)
                        total_latency_ms = _round((time.perf_counter() - overall_start) * 1000.0)
                        _http_client_latency.record(
                            total_latency_ms,
                            {
                                "tool": self.tool_id,
                                "method": method_upper,
                                "status_class": "error",
                            },
                        )
                        span.set_attribute("retry_count", retry_count)
                        raise error
                attempt_start = time.perf_counter()
                _log_json(
                    phase="send",
                    tool=self.tool_id,
                    method=method_upper,
                    url=url,
                    headers=redacted_headers,
                    attempt=attempt_number,
                    breaker_state=breaker_state,
                )
                try:
                    response = await self._client.request(
                        method_upper,
                        url,
                        headers=headers,
                        timeout=self._timeout,
                        **kwargs,
                    )
                    last_exception = None
                except Exception as exc:  # broad to map canonical error later
                    last_exception = exc
                    retry_reason = self._should_retry_exception(exc, is_idempotent)
                    if retry_reason and retry_count < self._config.retry_max:
                        retry_count += 1
                        span.add_event(
                            "retry",
                            {
                                "reason": retry_reason,
                                "attempt": retry_count,
                            },
                        )
                        _http_client_retries.add(1, {"tool": self.tool_id, "reason": retry_reason})
                        _log_json(
                            phase="retry",
                            tool=self.tool_id,
                            method=method_upper,
                            url=url,
                            reason=retry_reason,
                            attempt=retry_count,
                        )
                        await self._sleep(self._jitter_delay(retry_count))
                        continue
                    error = map_httpx_error(self.tool_id, exc)
                    _tool_errors_total.add(1, {"tool": self.tool_id, "code": error.code})
                    span.record_exception(exc)
                    span.set_status(Status(StatusCode.ERROR, error.code))
                    if self._breaker:
                        _, changed = self._breaker.record_failure()
                        span.set_attribute("breaker_state", self._breaker.state)
                        if changed:
                            _log_json(
                                phase="breaker",
                                tool=self.tool_id,
                                method=method_upper,
                                url=url,
                                breaker_state=self._breaker.state,
                            )
                    span.set_attribute("retry_count", retry_count)
                    total_latency_ms = _round((time.perf_counter() - overall_start) * 1000.0)
                    _http_client_latency.record(
                        total_latency_ms,
                        {
                            "tool": self.tool_id,
                            "method": method_upper,
                            "status_class": "error",
                        },
                    )
                    raise error

                latency_ms = _round((time.perf_counter() - attempt_start) * 1000.0)
                status_class = _status_class(response.status_code)
                span.set_attribute("http.status_code", response.status_code)
                span.set_attribute("breaker_state", breaker_state)
                _log_json(
                    phase="recv",
                    tool=self.tool_id,
                    method=method_upper,
                    url=url,
                    status=response.status_code,
                    latency_ms=latency_ms,
                    retry_count=retry_count,
                    breaker_state=breaker_state,
                )
                retry_after = None
                if response.headers.get("Retry-After"):
                    retry_after = _parse_retry_after(response.headers["Retry-After"])
                should_retry = self._should_retry_response(
                    response,
                    is_idempotent,
                    retry_after,
                )
                if should_retry and retry_count < self._config.retry_max:
                    retry_count += 1
                    reason = should_retry
                    span.add_event(
                        "retry",
                        {
                            "reason": reason,
                            "attempt": retry_count,
                        },
                    )
                    _http_client_retries.add(1, {"tool": self.tool_id, "reason": reason})
                    delay = retry_after if retry_after is not None else self._jitter_delay(retry_count)
                    _log_json(
                        phase="retry",
                        tool=self.tool_id,
                        method=method_upper,
                        url=url,
                        reason=reason,
                        attempt=retry_count,
                        delay_ms=_round(delay * 1000.0),
                    )
                    await self._sleep(delay)
                    continue
                break

            total_latency_ms = _round((time.perf_counter() - overall_start) * 1000.0)
            span.set_attribute("retry_count", retry_count)
            span.set_attribute("breaker_state", breaker_state)
            if last_exception is None and response is not None and response.status_code < 400:
                span.set_status(Status(StatusCode.OK))
            elif response is not None and response.status_code >= 400:
                span.set_status(Status(StatusCode.ERROR, str(response.status_code)))
            _http_client_latency.record(
                total_latency_ms,
                {
                    "tool": self.tool_id,
                    "method": method_upper,
                    "status_class": status_class,
                },
            )

            breaker_changed = False
            if self._breaker:
                if response is not None and response.status_code < 500:
                    _, breaker_changed = self._breaker.record_success()
                else:
                    _, breaker_changed = self._breaker.record_failure()
                if breaker_changed:
                    _log_json(
                        phase="breaker",
                        tool=self.tool_id,
                        method=method_upper,
                        url=url,
                        breaker_state=self._breaker.state,
                    )
                span.set_attribute("breaker_state", self._breaker.state)

            if response is not None and response.status_code >= 400:
                error = map_httpx_error(
                    self.tool_id,
                    httpx.HTTPStatusError(
                        "HTTP error",
                        request=response.request,
                        response=response,
                    ),
                )
                _tool_errors_total.add(1, {"tool": self.tool_id, "code": error.code})
                span.record_exception(error)
                span.set_status(Status(StatusCode.ERROR, error.code))
                raise error

            span.set_status(Status(StatusCode.OK))
            return response

    def _should_retry_exception(
        self,
        exc: Exception,
        idempotent: bool,
    ) -> Optional[str]:
        if isinstance(exc, httpx.TimeoutException):
            return "timeout"
        if isinstance(exc, httpx.RequestError) and idempotent:
            return "network"
        return None

    def _should_retry_response(
        self,
        response: httpx.Response,
        idempotent: bool,
        retry_after: Optional[float],
    ) -> Optional[str]:
        status = response.status_code
        if status == 429:
            return "retry_after" if retry_after is not None else "429"
        if status == 501:
            return None
        if 500 <= status < 600:
            if idempotent:
                return "5xx"
            return None
        if status in {408} and idempotent:
            return "408"
        return None


def _log_json(**fields: Any) -> None:
    span = trace.get_current_span()
    trace_id = span.get_span_context().trace_id if span.get_span_context().is_valid else 0
    payload = {
        "trace_id": f"{trace_id:032x}" if trace_id else "0" * 32,
    }
    payload.update(fields)
    payload = _normalise(payload)
    _logger.info(json.dumps(payload, sort_keys=True))


def _normalise(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: _normalise(value[k]) for k in sorted(value)}
    if isinstance(value, list):
        normalised = [_normalise(v) for v in value]
        if all(isinstance(v, dict) for v in normalised):
            return sorted(normalised, key=lambda item: json.dumps(item, sort_keys=True))
        return normalised
    if isinstance(value, float):
        return _round(value)
    return value
