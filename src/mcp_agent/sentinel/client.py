import hmac, hashlib, json, os, time
from typing import Optional

import httpx

class SentinelClient:
    def __init__(self, base_url: str, signing_key: str, http: Optional[httpx.Client]=None):
        self.base_url = base_url.rstrip("/")
        self.signing_key = signing_key.encode("utf-8")
        self.http = http or httpx.Client(timeout=3.0)

    def _sign(self, payload: dict) -> str:
        msg = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
        import hmac, hashlib
        return hmac.new(self.signing_key, msg, hashlib.sha256).hexdigest()

    def register(self, agent_id: str, version: str) -> None:
        payload = {"agent_id": agent_id, "version": version, "ts": int(time.time())}
        sig = self._sign(payload)
        r = self.http.post(f"{self.base_url}/v1/agents/register", json=payload, headers={"X-Signature": sig})
        r.raise_for_status()

    def authorize(self, project_id: str, run_type: str) -> bool:
        payload = {"project_id": project_id, "run_type": run_type}
        sig = self._sign(payload)
        r = self.http.post(f"{self.base_url}/v1/authorize", json=payload, headers={"X-Signature": sig})
        if r.status_code == 200:
            data = r.json()
            return bool(data.get("allow", False))
        if r.status_code == 403:
            return False
        r.raise_for_status()
        return False
