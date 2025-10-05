import pytest
import pytest_asyncio
import httpx
from mcp_agent.sentinel.client import SentinelClient


class MockDenyTransport(httpx.AsyncBaseTransport):
    """Mock transport that always denies authorization."""

    async def handle_async_request(self, request):
        return httpx.Response(
            403, json={"allow": False, "reason": "tier_inactive"}
        )


@pytest_asyncio.fixture
async def mock_sentinel_client():
    """Fixture providing a SentinelClient with deny mock transport."""
    async with httpx.AsyncClient(transport=MockDenyTransport()) as http:
        client = SentinelClient("http://sentinel", "k", http=http)
        yield client


@pytest.mark.asyncio
async def test_deny_returns_false(mock_sentinel_client):
    """Test that denied authorization returns False."""
    result = await mock_sentinel_client.authorize("p", "paid_run")
    assert result is False
