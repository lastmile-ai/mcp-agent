from typing import Any, Dict, Optional

from jsonschema import validate, ValidationError

from ..client.http import HTTPClient
from ..errors.canonical import CanonicalError, map_schema_error

class BaseAdapter:
    def __init__(self, tool: str, base_url: str, schema: Optional[Dict[str, Any]] = None, client: Optional[HTTPClient] = None):
        self.tool = tool
        self.client = client or HTTPClient(tool, base_url)
        self.schema = schema

    def _validate(self, data: Dict[str, Any]) -> Dict[str, Any]:
        if not self.schema:
            return data
        try:
            validate(data, self.schema)
            return data
        except ValidationError as e:
            raise map_schema_error(self.tool, e)

    def get(self, path: str) -> Dict[str, Any]:
        data = self.client.get_json(path)
        return self._validate(data)

    def post(self, path: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        data = self.client.post_json(path, json=payload)
        return self._validate(data)
