import pytest
import httpx
from mcp_agent.sentinel.client import SentinelClient


class MockDenyTransport(httpx.BaseTransport):
    """Mock transport that always denies authorization."""

    def handle_request(self, request):
        return httpx.Response(
            403, json={"allow": False, "reason": "tier_inactive"}
        )


@pytest.fixture
def mock_sentinel_client():
    """Fixture providing a SentinelClient with deny mock transport."""
    client = SentinelClient(
        "http://sentinel", "k", http=httpx.Client(transport=MockDenyTransport())
    )
    yield client
    # Cleanup if needed


def test_deny_returns_false(mock_sentinel_client):
    """Test that denied authorization returns False."""
    result = mock_sentinel_client.authorize("p", "paid_run")
    assert result is False
