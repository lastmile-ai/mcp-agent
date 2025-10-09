import json
import asyncio
from importlib import import_module

pub = import_module("mcp_agent.api.routes.public")
overlay = import_module("mcp_agent.api.routes.public_context_overlay")

class DummyApp:
    class _Router:
        def __init__(self): self.mounts = []
        def mount(self, path, router): self.mounts.append((path, router))
    def __init__(self): self.router = self._Router()

def test_overlay_mount():
    app = DummyApp()
    overlay.add_public_api_with_context(app)
    assert any(p=="/v1" for p,_ in app.router.mounts)
