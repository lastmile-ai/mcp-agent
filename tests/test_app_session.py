import pytest

from mcp_agent.app import MCPApp


@pytest.mark.asyncio
async def test_mcp_app_respects_session_id_override():
    app = MCPApp(session_id="resume-session-123")
    try:
        await app.initialize()
        assert app.session_id == "resume-session-123"
    finally:
        await app.cleanup()
