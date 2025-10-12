"""Utilities for redacting secrets from structured log records."""

from __future__ import annotations

import logging
import os
import re
from typing import Any, Iterable, Mapping, Sequence

SENSITIVE_FIELD_NAMES = {
    "authorization",
    "github_token",
    "github_personal_access_token",
}

REDACTED = "[REDACTED]"


def _secret_values_from_env() -> Iterable[str]:
    for key, value in os.environ.items():
        if not value:
            continue
        if key in {"GITHUB_TOKEN", "GITHUB_PERSONAL_ACCESS_TOKEN"}:
            yield value
        if key.endswith("_API_KEY"):
            yield value


_ENV_SECRETS = tuple(_secret_values_from_env())


class RedactionFilter(logging.Filter):
    """Logging filter that scrubs sensitive data from records."""

    _SKIP_KEYS = {
        "name",
        "msg",
        "args",
        "levelname",
        "levelno",
        "pathname",
        "filename",
        "module",
        "exc_info",
        "exc_text",
        "stack_info",
        "lineno",
        "funcName",
        "created",
        "msecs",
        "relativeCreated",
        "thread",
        "threadName",
        "processName",
        "process",
        "asctime",
    }

    def filter(self, record: logging.LogRecord) -> bool:  # pragma: no cover - exercised indirectly
        message = self._render_message(record.msg, record.args)
        record.msg = self._sanitize(message)
        record.args = ()

        for key, value in list(record.__dict__.items()):
            if key in self._SKIP_KEYS:
                continue
            record.__dict__[key] = self._sanitize(value)
        return True

    def _render_message(self, msg: Any, args: Any) -> str:
        if args:
            try:
                return str(msg) % args
            except Exception:
                return str(msg)
        return str(msg)

    def _sanitize(self, value: Any) -> Any:
        if isinstance(value, str):
            return self._sanitize_string(value)
        if isinstance(value, Mapping):
            return {k: self._sanitize_mapping_value(k, v) for k, v in value.items()}
        if isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray)):
            return [self._sanitize(v) for v in value]
        return value

    def _sanitize_mapping_value(self, key: str, value: Any) -> Any:
        key_norm = key.lower()
        if key_norm in SENSITIVE_FIELD_NAMES or key_norm.endswith("_api_key"):
            return REDACTED
        return self._sanitize(value)

    def _sanitize_string(self, raw: str) -> str:
        cleaned = raw
        if "authorization" in raw.lower():
            cleaned = re.sub(r"(?i)(authorization\s*[:=]\s*)(.+)", r"\1" + REDACTED, cleaned)
        for secret in _ENV_SECRETS:
            if secret and secret in cleaned:
                cleaned = cleaned.replace(secret, REDACTED)
        return cleaned


def install_redaction_filter(logger: logging.Logger | None = None) -> None:
    """Attach :class:`RedactionFilter` to the provided logger."""

    target = logger or logging.getLogger("mcp_agent")
    if any(isinstance(flt, RedactionFilter) for flt in target.filters):
        return
    target.addFilter(RedactionFilter())


__all__ = ["RedactionFilter", "install_redaction_filter", "REDACTED"]

