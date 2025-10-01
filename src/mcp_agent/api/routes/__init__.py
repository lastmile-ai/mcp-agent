from .public import router as public_router

def add_public_api(app):
    app.router.mount("/v1", public_router)
