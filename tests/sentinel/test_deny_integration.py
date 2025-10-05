import httpx
from mcp_agent.sentinel.client import SentinelClient

class MockTransport(httpx.BaseTransport):
    def handle_request(self, request):
        return httpx.Response(403, json={"allow": False, "reason": "tier_inactive"})

def test_deny_returns_false():
    c = SentinelClient("http://sentinel", "k", http=httpx.Client(transport=MockTransport()))
    assert c.authorize("p", "paid_run") is False
