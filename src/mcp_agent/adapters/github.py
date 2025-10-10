"""Concrete adapter for the Github MCP tool."""

from __future__ import annotations

from typing import Any, Dict, Optional

from pydantic import Field

from ..client.http import HTTPToolClient
from .base import BaseAdapter, StrictModel


class RepoRef(StrictModel):
    owner: str
    repo: str


class BranchDescriptor(StrictModel):
    default_branch: str


class FileStatResponse(StrictModel):
    exists: bool


class PutFileRequest(StrictModel):
    owner: str
    repo: str
    branch: str
    path: str
    content_b64: str
    mode: str = Field(pattern=r"^(add-only|overwrite)$")


class PutFileResponse(StrictModel):
    created: bool
    message: Optional[str] = None


class PullRequestRequest(StrictModel):
    owner: str
    repo: str
    base: str
    head: str
    title: str
    body: str


class PullRequestResponse(StrictModel):
    id: str


class WellKnownResponse(StrictModel):
    name: str
    version: str
    capabilities: Dict[str, Any]


class GithubMCPAdapter(BaseAdapter):
    tool_id = "github-mcp-server"

    def __init__(
        self,
        base_url: str,
        *,
        token: Optional[str] = None,
        client: Optional[HTTPToolClient] = None,
    ) -> None:
        headers: Dict[str, str] = {"Content-Type": "application/json"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        super().__init__(self.tool_id, base_url, default_headers=headers, client=client)

    async def describe(self) -> WellKnownResponse:
        result = await self._request_json("GET", "/.well-known/mcp", response_model=WellKnownResponse)
        return result

    async def get_default_branch(self, ref: RepoRef) -> BranchDescriptor:
        payload = await self._request_json(
            "GET",
            "/git/default_branch",
            params=ref.model_dump(),
            response_model=BranchDescriptor,
        )
        return payload

    async def stat(self, ref: RepoRef, branch: str, path: str) -> FileStatResponse:
        payload = await self._request_json(
            "GET",
            "/fs/stat",
            params={**ref.model_dump(), "ref": branch, "path": path},
            response_model=FileStatResponse,
        )
        return payload

    async def put_file(self, request: PutFileRequest) -> PutFileResponse:
        payload = await self._request_json(
            "PUT",
            "/fs/put",
            json=request.model_dump(),
            response_model=PutFileResponse,
            idempotent=True,
        )
        return payload

    async def open_pull_request(self, request: PullRequestRequest) -> PullRequestResponse:
        payload = await self._request_json(
            "POST",
            "/pr/create",
            json=request.model_dump(),
            response_model=PullRequestResponse,
        )
        return payload
