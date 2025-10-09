from __future__ import annotations

import json
from hashlib import sha256
from typing import Any, Dict, Optional

from .models import Manifest


def canonical_dumps(obj: Any) -> bytes:
    """
    Canonical JSON bytes: UTF-8, sorted keys, no whitespace.
    """
    return json.dumps(obj, sort_keys=True, separators=(",", ":")).encode("utf-8")


def compute_manifest_hash(
    manifest: Manifest,
    code_version: Optional[str] = None,
    tool_versions: Optional[Dict[str, str]] = None,
    settings_fingerprint: Optional[str] = None,
) -> str:
    """
    Hash is computed over the canonicalized manifest content plus a meta envelope
    that includes code/tool/settings fingerprints so equal content under different
    versions yields different hashes.
    """
    payload = {
        "slices": [s.model_dump() for s in manifest.slices],
        "code_version": code_version or "",
        "tool_versions": tool_versions or {},
        "settings_fingerprint": settings_fingerprint or "",
    }
    return sha256(canonical_dumps(payload)).hexdigest()
