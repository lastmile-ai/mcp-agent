import pytest
import httpx
from mcp_agent.sentinel.client import SentinelClient


class MockAuthorizeTransport(httpx.BaseTransport):
    """Mock transport for testing authorization matrix."""

    def handle_request(self, request):
        if request.url.path.endswith("/v1/authorize"):
            import json

            body = json.loads(request.content)
            if body["run_type"] == "free_run":
                return httpx.Response(200, json={"allow": True})
            return httpx.Response(403, json={"allow": False})
        return httpx.Response(404)


@pytest.fixture
def mock_sentinel_client():
    """Fixture providing a SentinelClient with mock transport."""
    client = SentinelClient(
        "http://sentinel", "k", http=httpx.Client(transport=MockAuthorizeTransport())
    )
    yield client
    # Cleanup if needed


@pytest.mark.parametrize(
    "project_id,run_type,expected",
    [
        ("p", "free_run", True),
        ("p", "paid_run", False),
    ],
)
def test_authorize_matrix(mock_sentinel_client, project_id, run_type, expected):
    """Test authorization matrix with parameterized inputs."""
    result = mock_sentinel_client.authorize(project_id, run_type)
    assert result is expected
