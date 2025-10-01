import re
from typing import Iterable

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

_PATTERNS = [
    re.compile(r"(Authorization:\s*Bearer\s+)[A-Za-z0-9-_\.]+", re.IGNORECASE),
    re.compile(r"(Authorization:\s*token\s+)[A-Za-z0-9_]+", re.IGNORECASE),
    re.compile(r"(ghp_)[A-Za-z0-9]{20,}"),
    re.compile(r"(github_pat_)[A-Za-z0-9_]{20,}"),
]

def redact_text(s: str) -> str:
    red = s
    for pat in _PATTERNS:
        red = pat.sub(r"\1[REDACTED]", red)
    return red

class RedactionMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        scope = request.scope
        headers = list(scope.get("headers", []))
        filtered = []
        for k, v in headers:
            if k.lower() == b"authorization":
                continue
            filtered.append((k, v))
        scope["headers"] = filtered
        resp = await call_next(request)
        resp.headers.pop("authorization", None)
        resp.headers.pop("Authorization", None)
        return resp
