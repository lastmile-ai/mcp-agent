from starlette.requests import Request
from starlette.responses import JSONResponse
from mcp_agent.tasks import bootstrap_repo

async def bootstrap_repo_handler(request: Request):
    body = await request.json()
    owner = body.get("owner")
    repo = body.get("repo")
    trace_id = body.get("trace_id","")
    language = body.get("language","auto")
    dry = bool(body.get("dry_run", False))
    if not owner or not repo:
        return JSONResponse({"error": "owner and repo required"}, status_code=400)
    out = bootstrap_repo.run(owner=owner, repo=repo, trace_id=trace_id, language=language, dry_run=dry)
    return JSONResponse(out, status_code=200)
