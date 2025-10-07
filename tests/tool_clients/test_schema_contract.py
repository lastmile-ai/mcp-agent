import httpx
import pytest

from mcp_agent.adapters.base import BaseAdapter
from mcp_agent.errors.canonical import CanonicalError

WANTED = {
    "type":"object",
    "properties": {"status":{"type":"string"}},
    "required": ["status"],
}

class BadShape(httpx.BaseTransport):
    def handle_request(self, request):
        return httpx.Response(200, json={"foo":1}, request=request)

def test_schema_validation_failure_maps_to_canonical_error():
    a = BaseAdapter(tool="tool-x", base_url="http://x", schema=WANTED, client=None)
    # inject transport into client's http layer
    from mcp_agent.client.http import HTTPClient
    a.client = HTTPClient("tool-x", "http://x", transport=BadShape())
    with pytest.raises(CanonicalError) as ei:
        a.get("/check")
    assert ei.value.code == "schema_validation_error"
