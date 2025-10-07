import base64
import os
from typing import Optional, Tuple

import httpx


class GithubMCPClient:
    def __init__(self, base_url: Optional[str] = None, token: Optional[str] = None, timeout: float = 30.0):
        self.base_url = (base_url or os.getenv("GITHUB_MCP_ENDPOINT") or "").rstrip("/")
        self.token = token or os.getenv("GITHUB_MCP_TOKEN") or ""
        self.timeout = timeout

    def _headers(self):
        h = {"Content-Type": "application/json"}
        if self.token:
            h["Authorization"] = f"Bearer {self.token}"
        return h

    def get_default_branch(self, owner: str, repo: str) -> str:
        r = httpx.get(f"{self.base_url}/git/default_branch", params={"owner": owner, "repo": repo}, headers=self._headers(), timeout=self.timeout)
        r.raise_for_status()
        return r.json().get("default_branch") or "main"

    def stat(self, owner: str, repo: str, ref: str, path: str) -> bool:
        r = httpx.get(f"{self.base_url}/fs/stat", params={"owner": owner, "repo": repo, "ref": ref, "path": path}, headers=self._headers(), timeout=self.timeout)
        if r.status_code == 404:
            return False
        r.raise_for_status()
        return True

    def create_branch(self, owner: str, repo: str, base: str, name: str) -> None:
        r = httpx.post(f"{self.base_url}/git/branches", json={"owner": owner, "repo": repo, "base": base, "name": name}, headers=self._headers(), timeout=self.timeout)
        r.raise_for_status()

    def put_add_only(self, owner: str, repo: str, branch: str, path: str, content: bytes) -> Tuple[bool, str]:
        body = {"owner": owner, "repo": repo, "branch": branch, "path": path, "content_b64": base64.b64encode(content).decode("ascii"), "mode": "add-only"}
        r = httpx.put(f"{self.base_url}/fs/put", json=body, headers=self._headers(), timeout=self.timeout)
        r.raise_for_status()
        data = r.json() if r.content else {}
        return bool(data.get("created", True)), data.get("message", "created")

    def open_pr(self, owner: str, repo: str, base: str, head: str, title: str, body: str) -> str:
        r = httpx.post(f"{self.base_url}/pr/create", json={"owner": owner, "repo": repo, "base": base, "head": head, "title": title, "body": body}, headers=self._headers(), timeout=self.timeout)
        r.raise_for_status()
        return str(r.json().get("id", ""))

    def run_ci_on_pr(self, owner: str, repo: str, pr_id: str) -> None:
        r = httpx.post(f"{self.base_url}/ci/run_workflow", json={"owner": owner, "repo": repo, "pr_id": pr_id}, headers=self._headers(), timeout=self.timeout)
        r.raise_for_status()
