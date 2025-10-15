from mcp_agent.context.telemetry import meter as meter
from .public import router as public_router
from .public_context_overlay import add_public_api_with_context as add_public_api_with_context


from starlette.routing import Route, Router

from .agent import router as agent_router
from .human_input import router as human_input_router
from .orchestrator import router as orchestrator_router
from .tool_registry import router as tool_registry_router
from .workflow_builder import router as workflow_builder_router

def _clone_route(route):
    if isinstance(route, Route):
        return Route(route.path, route.endpoint, methods=list(route.methods or []))
    return route


def add_admin_api(app, prefix: str = "/v1/admin") -> None:
    admin_router = Router()
    for source in (
        agent_router,
        tool_registry_router,
        orchestrator_router,
        workflow_builder_router,
        human_input_router,
    ):
        for route in source.routes:
            admin_router.routes.append(_clone_route(route))
    app.router.mount(prefix, admin_router)
def add_public_api(app):
    app.router.mount("/v1", public_router)

__all__ = ["add_public_api", "add_admin_api", "public_router"]
