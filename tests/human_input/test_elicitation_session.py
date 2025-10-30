import pytest

from types import SimpleNamespace
from unittest.mock import patch

from mcp_agent.core.context import Context
from mcp_agent.core.request_context import (
    reset_current_request_context,
    set_current_request_context,
)
from mcp_agent.human_input.elicitation_handler import elicitation_input_callback
from mcp_agent.human_input.types import HumanInputRequest


class _DummySession:
    def __init__(self) -> None:
        self.called_with = None

    async def elicit(self, **kwargs):
        self.called_with = kwargs
        return SimpleNamespace(action="accept", content={"response": "ack"})


@pytest.mark.asyncio
async def test_elicitation_uses_request_scoped_session():
    ctx = Context()
    session = _DummySession()
    ctx.upstream_session = session
    token = set_current_request_context(ctx)
    request = HumanInputRequest(prompt="hello", request_id="req-1")
    with patch("mcp_agent.core.context.get_current_context", return_value=ctx):
        try:
            response = await elicitation_input_callback(request)
        finally:
            reset_current_request_context(token)

    assert session.called_with is not None
    assert response.response == "ack"
