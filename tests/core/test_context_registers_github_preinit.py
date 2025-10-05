import pytest

from mcp_agent.core.context import Context, configure_context
from mcp_agent.config import Settings

def test_context_registers_github_preinit():
    ctx = Context()
    cfg = Settings()
    configure_context(ctx, cfg)
    assert hasattr(ctx, "server_registry")
    assert "github" in getattr(ctx.server_registry, "pre_init_hooks", {})
