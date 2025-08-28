"""API client implementation for the MCP Agent Cloud API."""

import json
from typing import Any, Dict, Optional

import httpx


class UnauthenticatedError(Exception):
    """Raised when the API client is unauthenticated (e.g., redirected to login)."""

    pass


def _raise_for_unauthenticated(response: httpx.Response):
    """Check if the response indicates an unauthenticated request.
    Raises:
        UnauthenticatedError: If the response status code is 401 or 403.
    """
    if response.status_code == 401 or (
        response.status_code == 307
        and "/api/auth/signin" in response.headers.get("location", "")
    ):
        raise UnauthenticatedError(
            "Unauthenticated request. Please check your API key or login status."
        )


def _raise_for_status_with_details(response: httpx.Response) -> None:
    try:
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        content_type = response.headers.get("content-type", "")
        if "application/json" in content_type:
            try:
                error_info = response.json()
                message = (
                    error_info.get("error")
                    or error_info.get("message")
                    or str(error_info)
                )
            except Exception:
                message = response.text
        else:
            message = response.text
        raise httpx.HTTPStatusError(
            f"{exc.response.status_code} Error for {exc.request.url}: {message}",
            request=exc.request,
            response=exc.response,
        ) from exc


class APIClient:
    """Client for interacting with the API service over HTTP."""

    def __init__(self, api_url: str, api_key: str):
        """Initialize the API client.

        Args:
            api_url: The base URL of the API (e.g., https://mcp-agent.com/api)
            api_key: The API authentication key
        """
        self.api_url = api_url.rstrip(
            "/"
        )  # Remove trailing slash for consistent URL building
        self.api_key = api_key

    def _get_headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    async def post(
        self, path: str, payload: Dict[str, Any], timeout: float = 30.0
    ) -> httpx.Response:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.api_url}/{path.lstrip('/')}",
                json=payload,
                headers=self._get_headers(),
                timeout=timeout,
            )
            _raise_for_unauthenticated(response)
            _raise_for_status_with_details(response)
            return response

    async def put(
        self, path: str, payload: Dict[str, Any], timeout: float = 30.0
    ) -> httpx.Response:
        async with httpx.AsyncClient() as client:
            response = await client.put(
                f"{self.api_url}/{path.lstrip('/')}",
                json=payload,
                headers=self._get_headers(),
                timeout=timeout,
            )
            _raise_for_unauthenticated(response)
            _raise_for_status_with_details(response)
            return response

    async def get(self, path: str, timeout: float = 30.0) -> httpx.Response:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.api_url}/{path.lstrip('/')}",
                headers=self._get_headers(),
                timeout=timeout,
            )
            _raise_for_unauthenticated(response)
            _raise_for_status_with_details(response)
            return response

    async def delete(
        self,
        path: str,
        payload: Optional[Dict[str, Any]] = None,
        timeout: float = 30.0,
    ) -> httpx.Response:
        async with httpx.AsyncClient() as client:
            response = await client.request(
                "DELETE",
                f"{self.api_url}/{path.lstrip('/')}",
                content=json.dumps(payload) if payload else None,
                headers=self._get_headers(),
                timeout=timeout,
            )
            _raise_for_unauthenticated(response)
            _raise_for_status_with_details(response)
            return response
