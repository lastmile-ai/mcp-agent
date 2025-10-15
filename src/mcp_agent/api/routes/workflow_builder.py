"""Routes for runtime workflow composition and editing."""

from __future__ import annotations

from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route, Router

from mcp_agent.models.workflow import (
    WorkflowDefinition,
    WorkflowPatch,
    WorkflowStep,
    WorkflowStepPatch,
)
from mcp_agent.workflows.composer import (
    WorkflowComposerError,
    WorkflowNotFoundError,
    workflow_composer,
)


async def list_workflows(_request: Request) -> JSONResponse:
    summaries = await workflow_composer.list()
    return JSONResponse({"items": [s.model_dump(mode="json") for s in summaries]})


async def create_workflow(request: Request) -> JSONResponse:
    definition = WorkflowDefinition(**(await request.json()))
    try:
        definition = await workflow_composer.create(definition)
    except WorkflowComposerError as exc:
        return JSONResponse({"error": str(exc)}, status_code=409)
    return JSONResponse(definition.model_dump(mode="json"), status_code=201)


async def get_workflow(request: Request) -> JSONResponse:
    workflow_id = request.path_params["workflow_id"]
    try:
        definition = await workflow_composer.get(workflow_id)
    except WorkflowNotFoundError:
        return JSONResponse({"error": "not_found"}, status_code=404)
    return JSONResponse(definition.model_dump(mode="json"))


async def patch_workflow(request: Request) -> JSONResponse:
    workflow_id = request.path_params["workflow_id"]
    patch = WorkflowPatch(**(await request.json()))
    try:
        definition = await workflow_composer.update(workflow_id, patch)
    except WorkflowNotFoundError:
        return JSONResponse({"error": "not_found"}, status_code=404)
    return JSONResponse(definition.model_dump(mode="json"))


async def delete_workflow(request: Request) -> JSONResponse:
    workflow_id = request.path_params["workflow_id"]
    try:
        await workflow_composer.delete(workflow_id)
    except WorkflowNotFoundError:
        return JSONResponse({"error": "not_found"}, status_code=404)
    return JSONResponse({}, status_code=204)


async def add_step(request: Request) -> JSONResponse:
    workflow_id = request.path_params["workflow_id"]
    body = await request.json()
    parent_id = body.get("parent_id")
    step_data = body.get("step")
    if not isinstance(parent_id, str) or not isinstance(step_data, dict):
        return JSONResponse({"error": "invalid_schema"}, status_code=400)
    new_step = WorkflowStep(**step_data)
    try:
        definition = await workflow_composer.add_step(workflow_id, parent_id, new_step)
    except WorkflowNotFoundError:
        return JSONResponse({"error": "not_found"}, status_code=404)
    return JSONResponse(definition.model_dump(mode="json"))


async def patch_step(request: Request) -> JSONResponse:
    workflow_id = request.path_params["workflow_id"]
    step_id = request.path_params["step_id"]
    patch = WorkflowStepPatch(**(await request.json()))
    try:
        definition = await workflow_composer.patch_step(workflow_id, step_id, patch)
    except WorkflowNotFoundError:
        return JSONResponse({"error": "not_found"}, status_code=404)
    return JSONResponse(definition.model_dump(mode="json"))


async def delete_step(request: Request) -> JSONResponse:
    workflow_id = request.path_params["workflow_id"]
    step_id = request.path_params["step_id"]
    try:
        definition = await workflow_composer.remove_step(workflow_id, step_id)
    except WorkflowNotFoundError:
        return JSONResponse({"error": "not_found"}, status_code=404)
    return JSONResponse(definition.model_dump(mode="json"))


routes = [
    Route("/workflows", list_workflows, methods=["GET"]),
    Route("/workflows", create_workflow, methods=["POST"]),
    Route("/workflows/{workflow_id}", get_workflow, methods=["GET"]),
    Route("/workflows/{workflow_id}", patch_workflow, methods=["PATCH"]),
    Route("/workflows/{workflow_id}", delete_workflow, methods=["DELETE"]),
    Route("/workflows/{workflow_id}/steps", add_step, methods=["POST"]),
    Route(
        "/workflows/{workflow_id}/steps/{step_id}",
        patch_step,
        methods=["PATCH"],
    ),
    Route(
        "/workflows/{workflow_id}/steps/{step_id}",
        delete_step,
        methods=["DELETE"],
    ),
]

router = Router(routes=routes)


def add_workflow_builder_api(app, prefix: str = "/v1/admin") -> None:
    if isinstance(app.router, Router):
        app.router.mount(prefix, router)
    else:  # pragma: no cover - Starlette compatibility
        app.mount(prefix, router)


__all__ = ["add_workflow_builder_api", "router"]
