To expose the endpoint, add the following to routes list in public.py:

from mcp_agent.api.routes.bootstrap_repo import bootstrap_repo_handler
...
routes = [
    Route("/runs", create_run, methods=["POST"]),
    Route("/stream/{id}", stream_run, methods=["GET"]),
    Route("/runs/{id}/cancel", cancel_run, methods=["POST"]),
    Route("/artifacts/{id}", get_artifact, methods=["GET"]),
    Route("/bootstrap/repo", bootstrap_repo_handler, methods=["POST"]),  # <-- add this line
]
