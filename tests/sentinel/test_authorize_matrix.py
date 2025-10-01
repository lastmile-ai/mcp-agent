import json
import httpx

from mcp_agent.sentinel.client import SentinelClient

class MockTransport(httpx.BaseTransport):
    def handle_request(self, request):
        if request.url.path.endswith("/v1/authorize"):
            body = json.loads(request.content)
            if body["run_type"] == "free_run":
                return httpx.Response(200, json={"allow": True})
            return httpx.Response(403, json={"allow": False})
        return httpx.Response(404)

def test_authorize_matrix():
    c = SentinelClient("http://sentinel", "k", http=httpx.Client(transport=MockTransport()))
    assert c.authorize("p", "free_run") is True
    assert c.authorize("p", "paid_run") is False
