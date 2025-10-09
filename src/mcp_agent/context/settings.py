from __future__ import annotations

import json
import os
from hashlib import sha256
from typing import Dict, Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class ContextSettings(BaseSettings):
    # Selection
    TOP_K: int = 25
    NEIGHBOR_RADIUS: int = 20

    # Timeouts per tool (ms)
    SEMANTIC_TIMEOUT_MS: int = 1000
    SYMBOLS_TIMEOUT_MS: int = 1000
    NEIGHBORS_TIMEOUT_MS: int = 1000
    PATTERNS_TIMEOUT_MS: int = 1000

    # Budgets
    TOKEN_BUDGET: Optional[int] = None
    MAX_FILES: Optional[int] = None
    SECTION_CAPS: Dict[int, int] = {}

    # Behavior
    ENFORCE_NON_DROPPABLE: bool = False

    # Logging and redaction
    REDACT_PATH_GLOBS: list[str] = []

    model_config = SettingsConfigDict(env_prefix="MCP_CONTEXT_", case_sensitive=False)

    def fingerprint(self) -> str:
        # Only include fields that affect assembly outcome
        material = {
            "TOP_K": self.TOP_K,
            "NEIGHBOR_RADIUS": self.NEIGHBOR_RADIUS,
            "SEMANTIC_TIMEOUT_MS": self.SEMANTIC_TIMEOUT_MS,
            "SYMBOLS_TIMEOUT_MS": self.SYMBOLS_TIMEOUT_MS,
            "NEIGHBORS_TIMEOUT_MS": self.NEIGHBORS_TIMEOUT_MS,
            "PATTERNS_TIMEOUT_MS": self.PATTERNS_TIMEOUT_MS,
            "TOKEN_BUDGET": self.TOKEN_BUDGET,
            "MAX_FILES": self.MAX_FILES,
            "SECTION_CAPS": self.SECTION_CAPS,
            "ENFORCE_NON_DROPPABLE": self.ENFORCE_NON_DROPPABLE,
        }
        blob = json.dumps(material, sort_keys=True, separators=(",", ":")).encode("utf-8")
        return sha256(blob).hexdigest()
