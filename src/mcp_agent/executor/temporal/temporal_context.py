from contextvars import ContextVar
from typing import Optional

EXECUTION_ID_KEY = "__execution_id"
PROXY_URL_KEY = "__proxy_url"

execution_id: ContextVar[Optional[str]] = ContextVar("execution_id", default=None)
proxy_url: ContextVar[Optional[str]] = ContextVar("proxy_url", default=None)
