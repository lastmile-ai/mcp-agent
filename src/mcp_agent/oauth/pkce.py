"""PKCE utilities."""

from __future__ import annotations

import base64
import hashlib
import secrets


def generate_code_verifier(length: int = 64) -> str:
    if length < 43 or length > 128:
        raise ValueError("PKCE code verifier length must be between 43 and 128")
    # token_urlsafe returns ~1.3 chars per byte; adjust to reach desired length
    needed_bytes = int(length * 0.8) + 1
    verifier = secrets.token_urlsafe(needed_bytes)
    if len(verifier) < length:
        verifier = (verifier + secrets.token_urlsafe(needed_bytes))[:length]
    return verifier[:length]


def generate_code_challenge(verifier: str) -> str:
    digest = hashlib.sha256(verifier.encode()).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode()


def generate_state(length: int = 32) -> str:
    return secrets.token_urlsafe(length)
