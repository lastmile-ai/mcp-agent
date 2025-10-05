import pytest
import httpx
from mcp_agent.sentinel.client import SentinelClient


class MockAuthorizeTransport(httpx.AsyncBaseTransport):
    """Mock transport for testing authorization matrix."""

    async def handle_async_request(self, request):
        if request.url.path.endswith("/v1/authorize"):
            import json

            body = json.loads(request.content)
            if body["run_type"] == "free_run":
                return httpx.Response(200, json={"allow": True})
            return httpx.Response(403, json={"allow": False})
        return httpx.Response(404)


@pytest.fixture
async def mock_sentinel_client():
    """Fixture providing a SentinelClient with mock transport."""
    async with httpx.AsyncClient(transport=MockAuthorizeTransport()) as http:
        client = SentinelClient("http://sentinel", "k", http=http)
        yield client


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "project_id,run_type,expected",
    [
        ("p", "free_run", True),
        ("p", "paid_run", False),
    ],
)
async def test_authorize_matrix(mock_sentinel_client, project_id, run_type, expected):
    """Test authorization matrix with parameterized inputs."""
    result = await mock_sentinel_client.authorize(project_id, run_type)
    assert result is expected
