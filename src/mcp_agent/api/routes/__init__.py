from mcp_agent.context.telemetry import meter
from .public import router as public_router
from .public_context_overlay import add_public_api_with_context

def add_public_api(app):
    app.router.mount("/v1", public_router)
