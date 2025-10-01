import datetime as dt
import os
from contextlib import asynccontextmanager
from typing import Any, Dict, Optional

import httpx
import jwt
from prometheus_client import Counter

# Telemetry
secret_issuance_total = Counter(
    "secret_issuance_total",
    "Count of secrets issued by type",
    ["kind"],
)
secret_revocation_total = Counter(
    "secret_revocation_total",
    "Count of secrets revoked/cleared by type",
    ["kind"],
)

GITHUB_API = os.getenv("GITHUB_API", "https://api.github.com")


def _now_utc() -> dt.datetime:
    return dt.datetime.now(tz=dt.timezone.utc)


def _clamp_ttl(seconds: int, default: int = 900, max_seconds: int = 900) -> int:
    """Clamp TTL to sane default and max (GitHub max 60m, default 15m)."""
    if seconds <= 0:
        return default
    return min(seconds, max_seconds)


def _load_github_app_creds() -> tuple[str, str]:
    app_id = os.getenv("GITHUB_APP_ID")
    pem = os.getenv("GITHUB_PRIVATE_KEY", "")
    if not app_id or not pem:
        raise RuntimeError("GITHUB_APP_ID and GITHUB_PRIVATE_KEY must be set")
    return app_id, pem


def _build_github_app_jwt(app_id: str, pem: str, ttl: int = 540) -> str:
    """Build a GitHub App JWT (≤10m)."""
    now = int(_now_utc().timestamp())
    payload = {"iat": now - 60, "exp": now + min(ttl, 600), "iss": app_id}
    token = jwt.encode(payload, pem, algorithm="RS256")
    if isinstance(token, bytes):
        token = token.decode()
    return token


async def issue_github_installation_token(
    installation_id: int,
    permissions: Optional[Dict[str, str]] = None,
    repositories: Optional[list[str]] = None,
    ttl_seconds: int = 900,
    http: Optional[httpx.AsyncClient] = None,
) -> dict:
    """Request a GitHub App installation access token (scoped, short-lived).
    Returns: { 'token': str, 'expires_at': ISO8601 }
    """
    app_id, pem = _load_github_app_creds()
    app_jwt = _build_github_app_jwt(app_id, pem)
    _ = _clamp_ttl(ttl_seconds, default=900, max_seconds=3600)  # recorded for policy, GitHub ignores TTL in request
    client = http or httpx.AsyncClient(timeout=5.0)
    close_client = http is None
    try:
        url = f"{GITHUB_API}/app/installations/{installation_id}/access_tokens"
        body: Dict[str, Any] = {}
        if permissions:
            body["permissions"] = permissions
        if repositories is not None:
            body["repositories"] = repositories
        headers = {
            "Authorization": f"Bearer {app_jwt}",
            "Accept": "application/vnd.github+json",
        }
        resp = await client.post(url, json=body, headers=headers)
        resp.raise_for_status()
        data = resp.json()
        token = data.get("token", "")
        if not token:
            raise RuntimeError("GitHub did not return an installation token")
        secret_issuance_total.labels(kind="github-installation").inc()
        return {"token": token, "expires_at": data.get("expires_at")}
    finally:
        if close_client:
            await client.aclose()


@asynccontextmanager
async def mount_github_token_for_run(
    target: str,
    installation_id: int,
    permissions: Optional[Dict[str, str]] = None,
    repositories: Optional[list[str]] = None,
    ttl_seconds: int = 900,
):
    """Issue token and expose only to the intended target for the run duration.
    Yields: object with `as_header()` to obtain Authorization header.
    """
    if target != "github-mcp-server":
        # Strict scope: do not allow mounting to arbitrary services
        raise ValueError("Only 'github-mcp-server' is authorized for GitHub token mounts")

    info = await issue_github_installation_token(
        installation_id=installation_id,
        permissions=permissions,
        repositories=repositories,
        ttl_seconds=ttl_seconds,
    )
    token = info["token"]

    class _Token:
        def as_header(self) -> Dict[str, str]:
            return {"Authorization": f"token {token}"}

        def raw(self) -> str:
            return token

    try:
        yield _Token()
    finally:
        # Best-effort cleanup; actual revocation is server-side by GitHub expiry
        secret_revocation_total.labels(kind="github-installation").inc()
        # Zero out local reference
        tb = bytearray(token.encode("utf-8"))
        for i in range(len(tb)):
            tb[i] = 0
        del tb
