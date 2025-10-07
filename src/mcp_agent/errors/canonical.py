from dataclasses import dataclass
from typing import Optional

import httpx
from jsonschema import ValidationError

@dataclass
class CanonicalError(Exception):
    tool: str
    code: str
    http: Optional[int]
    detail: str
    hint: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "tool": self.tool,
            "code": self.code,
            "http": self.http,
            "detail": self.detail,
            "hint": self.hint,
        }

def map_httpx_error(tool: str, e: Exception) -> CanonicalError:
    if isinstance(e, httpx.TimeoutException):
        return CanonicalError(tool, "timeout", None, "request timed out", "increase HTTP_TIMEOUT_MS or fix server")
    if isinstance(e, httpx.HTTPStatusError):
        return CanonicalError(tool, "http_error", e.response.status_code, f"http {e.response.status_code}", None)
    if isinstance(e, httpx.TransportError):
        return CanonicalError(tool, "network_error", None, "network error", None)
    return CanonicalError(tool, "unknown_error", None, str(e), None)

def map_schema_error(tool: str, e: ValidationError) -> CanonicalError:
    return CanonicalError(tool, "schema_validation_error", None, e.message, "/".join(str(p) for p in e.path))
