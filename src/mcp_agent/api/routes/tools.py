from starlette.responses import JSONResponse
from starlette.routing import Route, Router

from ...registry.store import store

async def get_tools(request):
    items = await store.get_all()
    return JSONResponse({"tools": items})

routes = [Route("/tools", get_tools, methods=["GET"])]
router = Router(routes=routes)

def add_tools_api(app):
    """Mount the tools API under /v1."""
    app.router.mount("/v1", router)
