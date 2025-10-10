"""Canonical error definitions for MCP tool clients."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

import httpx
from opentelemetry import trace
from pydantic import ValidationError

_TRACE_ID_PAD = "0" * 32
_SECRET_FIELD_PATTERN = re.compile(
    r"(?i)(authorization|x-signature|[a-z0-9\-]*key|token)\s*[:=]\s*([^\s,]+)"
)


def _current_trace_id() -> str:
    span = trace.get_current_span()
    context = span.get_span_context()
    if context is None or not context.is_valid:
        return _TRACE_ID_PAD
    return f"{context.trace_id:032x}"


def _scrub_detail(detail: Optional[str]) -> Optional[str]:
    if detail is None:
        return None
    return _SECRET_FIELD_PATTERN.sub(lambda m: f"{m.group(1)}=<redacted>", detail)


@dataclass(slots=True)
class CanonicalError(Exception):
    """Standard error payload emitted by tool clients."""

    tool: str
    code: str
    http: Optional[int]
    detail: Optional[str]
    hint: Optional[str]
    trace_id: str

    def __init__(
        self,
        tool: str,
        code: str,
        http: Optional[int] = None,
        detail: Optional[str] = None,
        hint: Optional[str] = None,
        trace_id: Optional[str] = None,
    ) -> None:
        Exception.__init__(self, detail or code)
        self.tool = tool
        self.code = code
        self.http = http
        self.detail = _scrub_detail(detail)
        self.hint = hint
        self.trace_id = trace_id or _current_trace_id()

    def to_dict(self) -> dict[str, Optional[str]]:
        return {
            "tool": self.tool,
            "code": self.code,
            "http": self.http,
            "detail": self.detail,
            "hint": self.hint,
            "trace_id": self.trace_id,
        }


def map_httpx_error(tool: str, exc: Exception) -> CanonicalError:
    """Map an httpx exception to a canonical error."""

    if isinstance(exc, CanonicalError):
        return exc

    if isinstance(exc, httpx.TimeoutException):
        return CanonicalError(
            tool,
            code="network_timeout",
            detail="HTTP request timed out",
            hint="increase HTTP_TIMEOUT_MS or fix server",
        )

    if isinstance(exc, httpx.TransportError):
        code = "network_error"
        detail = str(exc)
        if isinstance(exc, httpx.ProxyError):
            hint = "check proxy configuration"
        elif isinstance(exc, httpx.ConnectError):
            hint = "verify MCP tool endpoint is reachable"
        else:
            hint = None
        return CanonicalError(tool, code=code, detail=detail, hint=hint)

    if isinstance(exc, httpx.HTTPStatusError):
        status = exc.response.status_code
        if status == 429:
            return CanonicalError(
                tool,
                code="rate_limited",
                http=status,
                detail="upstream returned 429",
                hint="honor Retry-After",
            )
        if status == 401:
            return CanonicalError(tool, code="unauthorized", http=status, detail="401 unauthorized")
        if status == 403:
            return CanonicalError(tool, code="forbidden", http=status, detail="403 forbidden")
        if status == 404:
            return CanonicalError(tool, code="not_found", http=status, detail="404 not found")
        if 500 <= status < 600:
            return CanonicalError(
                tool,
                code="upstream_error",
                http=status,
                detail=f"upstream returned {status}",
            )
        return CanonicalError(tool, code="http_error", http=status, detail=f"http {status}")

    return CanonicalError(tool, code="unknown_error", detail=str(exc))


def map_validation_error(tool: str, exc: ValidationError) -> CanonicalError:
    first_error = exc.errors()[0] if exc.errors() else None
    path = "".join(f"[{str(p)}]" for p in first_error.get("loc", [])) if first_error else None
    message = first_error.get("msg") if first_error else str(exc)
    detail = f"validation failed at {path}: {message}" if path else f"validation failed: {message}"
    return CanonicalError(tool, code="schema_validation_error", detail=detail)


class CircuitOpenError(CanonicalError):
    def __init__(self, tool: str, detail: Optional[str] = None) -> None:
        super().__init__(tool=tool, code="circuit_open", http=None, detail=detail or "circuit breaker open")
