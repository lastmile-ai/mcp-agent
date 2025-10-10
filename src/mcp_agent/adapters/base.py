"""Typed base adapter for MCP tool clients."""

from __future__ import annotations

from typing import Any, Dict, Optional, Type, TypeVar

import httpx
from pydantic import BaseModel, ConfigDict, TypeAdapter, ValidationError

from ..client.http import HTTPClientConfig, HTTPToolClient
from ..errors.canonical import map_validation_error

_ResponseModel = TypeVar("_ResponseModel", bound=BaseModel)


class StrictModel(BaseModel):
    """Base Pydantic model enforcing strict validation."""

    model_config = ConfigDict(extra="forbid", arbitrary_types_allowed=False, str_strip_whitespace=True)


class BaseAdapter:
    """Base class for MCP tool adapters."""

    def __init__(
        self,
        tool_id: str,
        base_url: str,
        *,
        default_headers: Optional[Dict[str, str]] = None,
        client: Optional[HTTPToolClient] = None,
        config: Optional[HTTPClientConfig] = None,
    ) -> None:
        self.tool_id = tool_id
        self._default_headers = default_headers or {}
        self._client = client or HTTPToolClient(tool_id, base_url, config=config)

    @property
    def client(self) -> HTTPToolClient:
        return self._client

    def _is_idempotent(self, method: str, path: str) -> bool:
        if method.upper() == "POST":
            return False
        return True

    async def _request_json(
        self,
        method: str,
        path: str,
        *,
        params: Optional[Dict[str, Any]] = None,
        json: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
        response_model: Optional[Type[_ResponseModel]] = None,
        idempotent: Optional[bool] = None,
        **kwargs: Any,
    ) -> Dict[str, Any] | _ResponseModel:
        merged_headers = {**self._default_headers, **(headers or {})}
        response = await self._client.request(
            method,
            path,
            params=params,
            json=json,
            headers=merged_headers,
            idempotent=idempotent if idempotent is not None else self._is_idempotent(method, path),
            **kwargs,
        )
        payload = response.json()
        payload = _normalise(payload)
        if response_model is None:
            return payload
        try:
            adapter = TypeAdapter(response_model)
            return adapter.validate_python(payload)
        except ValidationError as exc:
            raise map_validation_error(self.tool_id, exc) from exc

    async def _request_stream(
        self,
        method: str,
        path: str,
        *,
        headers: Optional[Dict[str, str]] = None,
        idempotent: Optional[bool] = None,
        **kwargs: Any,
    ) -> httpx.Response:
        merged_headers = {**self._default_headers, **(headers or {})}
        response = await self._client.request(
            method,
            path,
            headers=merged_headers,
            idempotent=idempotent if idempotent is not None else self._is_idempotent(method, path),
            **kwargs,
        )
        return response

    def _validate(self, model: Type[_ResponseModel], data: Any) -> _ResponseModel:
        try:
            adapter = TypeAdapter(model)
            return adapter.validate_python(data)
        except ValidationError as exc:
            raise map_validation_error(self.tool_id, exc) from exc


def _normalise(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: _normalise(value[k]) for k in sorted(value)}
    if isinstance(value, list):
        normalised = [_normalise(v) for v in value]
        if all(isinstance(item, dict) for item in normalised):
            return sorted(normalised, key=lambda item: _normalise_key(item))
        return normalised
    if isinstance(value, float):
        return round(value, 6)
    return value


def _normalise_key(value: Dict[str, Any]) -> str:
    return ":".join(f"{key}={value[key]}" for key in sorted(value))
