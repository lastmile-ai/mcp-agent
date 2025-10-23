"""API client implementation for the MCP Agent Cloud API."""

import json
import uuid
from typing import Any, Dict, Optional

import httpx
from opentelemetry import trace
from opentelemetry.propagate import inject


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

    def __init__(self, api_url: str, api_key: str, trace_id: Optional[str] = None):
        """Initialize the API client.

        Args:
            api_url: The base URL of the API (e.g., https://mcp-agent.com/api)
            api_key: The API authentication key
            trace_id: Optional trace ID for the CLI process lifecycle (generated if not provided)
        """
        self.api_url = api_url.rstrip(
            "/"
        )  # Remove trailing slash for consistent URL building
        self.api_key = api_key
        # Generate or use provided trace ID for CLI process lifecycle
        self.trace_id = trace_id or str(uuid.uuid4())
        # Get tracer for API client operations
        self.tracer = trace.get_tracer(__name__)

    def _get_headers(self) -> Dict[str, str]:
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

        # Inject OpenTelemetry trace context headers
        trace_headers = {}
        inject(trace_headers)
        headers.update(trace_headers)

        # Add custom trace ID header for process lifecycle tracking
        headers["X-MCP-Trace-Id"] = self.trace_id

        return headers

    async def post(
        self, path: str, payload: Dict[str, Any], timeout: float = 30.0
    ) -> httpx.Response:
        with self.tracer.start_as_current_span(
            f"api.post.{path.replace('/', '.')}",
            attributes={
                "http.method": "POST",
                "http.url": f"{self.api_url}/{path.lstrip('/')}",
                "mcp.trace_id": self.trace_id,
            },
        ) as span:
            try:
                async with httpx.AsyncClient() as client:
                    response = await client.post(
                        f"{self.api_url}/{path.lstrip('/')}",
                        json=payload,
                        headers=self._get_headers(),
                        timeout=timeout,
                    )
                    span.set_attribute("http.status_code", response.status_code)
                    _raise_for_unauthenticated(response)
                    _raise_for_status_with_details(response)
                    return response
            except Exception as e:
                span.record_exception(e)
                raise

    async def put(
        self, path: str, payload: Dict[str, Any], timeout: float = 30.0
    ) -> httpx.Response:
        with self.tracer.start_as_current_span(
            f"api.put.{path.replace('/', '.')}",
            attributes={
                "http.method": "PUT",
                "http.url": f"{self.api_url}/{path.lstrip('/')}",
                "mcp.trace_id": self.trace_id,
            },
        ) as span:
            try:
                async with httpx.AsyncClient() as client:
                    response = await client.put(
                        f"{self.api_url}/{path.lstrip('/')}",
                        json=payload,
                        headers=self._get_headers(),
                        timeout=timeout,
                    )
                    span.set_attribute("http.status_code", response.status_code)
                    _raise_for_unauthenticated(response)
                    _raise_for_status_with_details(response)
                    return response
            except Exception as e:
                span.record_exception(e)
                raise

    async def get(self, path: str, timeout: float = 30.0) -> httpx.Response:
        with self.tracer.start_as_current_span(
            f"api.get.{path.replace('/', '.')}",
            attributes={
                "http.method": "GET",
                "http.url": f"{self.api_url}/{path.lstrip('/')}",
                "mcp.trace_id": self.trace_id,
            },
        ) as span:
            try:
                async with httpx.AsyncClient() as client:
                    response = await client.get(
                        f"{self.api_url}/{path.lstrip('/')}",
                        headers=self._get_headers(),
                        timeout=timeout,
                    )
                    span.set_attribute("http.status_code", response.status_code)
                    _raise_for_unauthenticated(response)
                    _raise_for_status_with_details(response)
                    return response
            except Exception as e:
                span.record_exception(e)
                raise

    async def delete(
        self,
        path: str,
        payload: Optional[Dict[str, Any]] = None,
        timeout: float = 30.0,
    ) -> httpx.Response:
        with self.tracer.start_as_current_span(
            f"api.delete.{path.replace('/', '.')}",
            attributes={
                "http.method": "DELETE",
                "http.url": f"{self.api_url}/{path.lstrip('/')}",
                "mcp.trace_id": self.trace_id,
            },
        ) as span:
            try:
                async with httpx.AsyncClient() as client:
                    response = await client.request(
                        "DELETE",
                        f"{self.api_url}/{path.lstrip('/')}",
                        content=json.dumps(payload) if payload else None,
                        headers=self._get_headers(),
                        timeout=timeout,
                    )
                    span.set_attribute("http.status_code", response.status_code)
                    _raise_for_unauthenticated(response)
                    _raise_for_status_with_details(response)
                    return response
            except Exception as e:
                span.record_exception(e)
                raise
