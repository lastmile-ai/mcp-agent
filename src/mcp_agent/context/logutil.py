from __future__ import annotations
import logging
from fnmatch import fnmatch
from typing import Dict, Iterable
_logger = logging.getLogger("mcp_agent.context")
if not _logger.handlers:
    _logger.setLevel(logging.INFO)
    _h = logging.StreamHandler()
    _fmt = logging.Formatter('%(asctime)s %(levelname)s %(name)s %(message)s')
    _h.setFormatter(_fmt)
    _logger.addHandler(_h)
def redact_path(path: str, globs: Iterable[str]) -> str:
    for g in globs or []:
        if fnmatch(path, g):
            return "<redacted>"
    return path
def redact_event(evt: Dict, globs: Iterable[str]) -> Dict:
    out = {}
    for k, v in evt.items():
        if isinstance(v, str) and (k in ("uri", "path", "file", "artifact")):
            out[k] = redact_path(v, globs)
        elif isinstance(v, dict):
            out[k] = redact_event(v, globs)
        elif isinstance(v, list):
            out[k] = [redact_event(x, globs) if isinstance(x, dict) else x for x in v]
        else:
            out[k] = v
    return out
def log_structured(**fields):
    _logger.info("struct", extra={"data": redact_event(fields, fields.get("redact_globs", []))})
