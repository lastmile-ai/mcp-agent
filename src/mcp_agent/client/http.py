import time
import os
from typing import Any, Dict, Optional
import httpx

# Try to import prometheus_client, provide dummy classes if unavailable
try:
    from prometheus_client import Histogram, Counter
except ImportError:
    # Dummy classes for test collection without prometheus_client
    class _DummyHistogram:
        def __init__(self, *args, **kwargs):
            pass
        def labels(self, **kwargs):
            return self
        def observe(self, value):
            pass
    
    class _DummyCounter:
        def __init__(self, *args, **kwargs):
            pass
        def labels(self, **kwargs):
            return self
        def inc(self):
            pass
    
    Histogram = _DummyHistogram
    Counter = _DummyCounter

# Telemetry
latency_ms = Histogram(
    "latency_ms",
    "HTTP latency by tool",
    ["tool"],
    buckets=(5,10,25,50,100,250,500,1000,2500,5000),
)
tool_errors_total = Counter(
    "tool_errors_total",
    "Canonical tool errors by code",
    ["code"],
)

# Config
_HTTP_TIMEOUT_MS = int(os.getenv("HTTP_TIMEOUT_MS", "3000"))
_RETRY_MAX = int(os.getenv("RETRY_MAX", "2"))
_BREAKER_THRESH = int(os.getenv("BREAKER_THRESH", "5"))
_BACKOFF_MS = int(os.getenv("BACKOFF_MS", "50"))
_BREAKER_COOLDOWN_MS = int(os.getenv("BREAKER_COOLDOWN_MS", "30000"))

class CircuitBreaker:
    def __init__(self, threshold: int = _BREAKER_THRESH, cooldown_ms: int = _BREAKER_COOLDOWN_MS):
        self.threshold = max(1, threshold)
        self.cooldown_ms = cooldown_ms
        self.failures = 0
        self.open_until_ms = 0

    def allow(self) -> bool:
        return int(time.time() * 1000) >= self.open_until_ms

    def record_ok(self) -> None:
        self.failures = 0
        self.open_until_ms = 0

    def record_fail(self) -> None:
        self.failures += 1
        if self.failures >= self.threshold:
            self.open_until_ms = int(time.time() * 1000) + self.cooldown_ms

class HTTPClient:
    def __init__(self, tool: str, base_url: str, transport: Optional[httpx.BaseTransport] = None):
        self.tool = tool
        self.base_url = base_url.rstrip("/")
        self.cb = CircuitBreaker()
        self._timeout = httpx.Timeout(_HTTP_TIMEOUT_MS / 1000.0)
        self._transport = transport

    def _sleep(self, ms: int) -> None:
        time.sleep(ms / 1000.0)

    def _request(self, method: str, path: str, **kwargs) -> httpx.Response:
        if not self.cb.allow():
            from ..errors.canonical import CanonicalError
            raise CanonicalError(tool=self.tool, code="circuit_open", http=None, detail="breaker open", hint="cooldown")
        url = f"{self.base_url}{'' if path.startswith('/') else '/'}{path}"
        attempt = 0
        last_exc = None
        while attempt <= _RETRY_MAX:
            try:
                with httpx.Client(timeout=self._timeout, transport=self._transport) as c:
                    start = time.time()
                    r = c.request(method, url, **kwargs)
                    latency_ms.labels(self.tool).observe((time.time() - start) * 1000.0)
                if r.status_code >= 500:
                    raise httpx.HTTPStatusError("server error", request=r.request, response=r)
                self.cb.record_ok()
                return r
            except (httpx.TimeoutException, httpx.TransportError, httpx.HTTPStatusError) as e:
                last_exc = e
                self.cb.record_fail()
                if attempt == _RETRY_MAX:
                    break
                self._sleep(_BACKOFF_MS * (attempt + 1))
                attempt += 1
        from ..errors.canonical import map_httpx_error
        err = map_httpx_error(self.tool, last_exc)
        tool_errors_total.labels(code=err.code).inc()
        raise err

    def get_json(self, path: str, **kwargs) -> Dict[str, Any]:
        r = self._request("GET", path, **kwargs)
        return r.json()

    def post_json(self, path: str, json: Dict[str, Any], **kwargs) -> Dict[str, Any]:
        r = self._request("POST", path, json=json, **kwargs)
        return r.json()
