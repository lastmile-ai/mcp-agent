"""Basic MCP mcp-agent app integration with OpenAI Apps SDK.

The server exposes widget-backed tools that render the UI bundle within the
client directory. Each handler returns the HTML shell via an MCP resource and
returns structured content so the ChatGPT client can hydrate the widget."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any, Dict, List

from starlette.routing import Mount
from starlette.staticfiles import StaticFiles
import uvicorn
from pathlib import Path
import mcp.types as types
from mcp.server.fastmcp import FastMCP
from mcp_agent.app import MCPApp
from mcp_agent.server.app_server import create_mcp_server_for_app


@dataclass(frozen=True)
class TimerWidget:
    identifier: str
    title: str
    template_uri: str
    invoking: str
    invoked: str
    html: str
    response_text: str


BUILD_DIR = Path(__file__).parent / "web" / "build"
ASSETS_DIR = BUILD_DIR / "static"

# Providing the JS and CSS to the app can be done in 1 of 2 ways:
# 1) Load the content as text from the static build files and inline them into the HTML template
# 2) (Preferred) Reference the static files served from the deployed server
# Since (2) depends on an initial deployment of the server, it is recommended to use approach (1) first
# and then switch to (2) once the server is deployed and its URL is available.
# (2) is preferred since (1) can lead to large HTML templates and potential for string escaping issues.


# Make sure these paths align with the build output paths (dynamic per build)
JS_PATH = ASSETS_DIR / "js" / "main.50dd757e.js"
CSS_PATH = ASSETS_DIR / "css" / "main.bf8e60c9.css"


# METHOD 1: Inline the JS and CSS into the HTML template
TIMER_JS = JS_PATH.read_text(encoding="utf-8")
TIMER_CSS = CSS_PATH.read_text(encoding="utf-8")

INLINE_HTML_TEMPLATE = f"""
<div id="coinflip-root"></div>
<style>
{TIMER_CSS}
</style>
<script type="module">
{TIMER_JS}
</script>
"""

# METHOD 2: Reference the static files from the deployed server
SERVER_URL = "https://<server_id>.deployments.mcp-agent.com"  # e.g. "https://15da9n6bk2nj3wiwf7ghxc2fy7sc6c8a.deployments.mcp-agent.com"
DEPLOYED_HTML_TEMPLATE = (
    '<div id="timer-root"></div>\n'
    f'<link rel="stylesheet" href="{SERVER_URL}/static/css/main.bf8e60c9.css">\n'
    f'<script type="module" src="{SERVER_URL}/static/js/main.50dd757e.js"></script>'
)


WIDGET = TimerWidget(
    identifier="timer",
    title="Timer",
    # OpenAI Apps heavily cache resource by URI, so use a date-based URI to bust the cache when updating the app.
    template_uri="ui://widget/timer-10-30-2025-12-00.html",
    invoking="Preparing timer",
    invoked="Starting the timer...",
    html=INLINE_HTML_TEMPLATE,  # Use INLINE_HTML_TEMPLATE or DEPLOYED_HTML_TEMPLATE
    response_text="Timer started! The timer will count down from the specified duration.",
)


MIME_TYPE = "text/html+skybridge"

mcp = FastMCP(
    name="timer",
    stateless_http=True,
)
app = MCPApp(
    name="timer",
    description="Timer widget for counting down within an OpenAI chat",
    mcp=mcp,
)


def _resource_description() -> str:
    return "Timer widget markup"


def _tool_meta() -> Dict[str, Any]:
    return {
        "openai/outputTemplate": WIDGET.template_uri,
        "openai/toolInvocation/invoking": WIDGET.invoking,
        "openai/toolInvocation/invoked": WIDGET.invoked,
        "openai/widgetAccessible": True,
        "openai/resultCanProduceWidget": True,
        "annotations": {
            "destructiveHint": False,
            "openWorldHint": False,
            "readOnlyHint": True,
        },
    }


def _embedded_widget_resource() -> types.EmbeddedResource:
    return types.EmbeddedResource(
        type="resource",
        resource=types.TextResourceContents(
            uri=WIDGET.template_uri,
            mimeType=MIME_TYPE,
            text=WIDGET.html,
            title=WIDGET.title,
        ),
    )


@mcp._mcp_server.list_tools()
async def _list_tools() -> List[types.Tool]:
    return [
        types.Tool(
            name=WIDGET.identifier,
            title=WIDGET.title,
            inputSchema={
                "type": "object",
                "properties": {
                    "hours": {
                        "type": "integer",
                        "description": "Number of hours for the timer (0-23)",
                        "minimum": 0,
                        "default": 0,
                    },
                    "minutes": {
                        "type": "integer",
                        "description": "Number of minutes for the timer (0-59)",
                        "minimum": 0,
                        "maximum": 59,
                        "default": 0,
                    },
                    "seconds": {
                        "type": "integer",
                        "description": "Number of seconds for the timer (0-59)",
                        "minimum": 0,
                        "maximum": 59,
                        "default": 0,
                    },
                    "message": {
                        "type": "string",
                        "description": "Optional message to display under the timer (e.g., '🥚 Soft boil eggs', '☕️ Coffee brewing', '📗 Study time!'). If not provided, shows default countdown message.",
                        "default": "",
                    },
                },
                "required": [],
            },
            description="Start a countdown timer with specified hours, minutes, and seconds",
            _meta=_tool_meta(),
        )
    ]


@mcp._mcp_server.list_resources()
async def _list_resources() -> List[types.Resource]:
    return [
        types.Resource(
            name=WIDGET.title,
            title=WIDGET.title,
            uri=WIDGET.template_uri,
            description=_resource_description(),
            mimeType=MIME_TYPE,
            _meta=_tool_meta(),
        )
    ]


@mcp._mcp_server.list_resource_templates()
async def _list_resource_templates() -> List[types.ResourceTemplate]:
    return [
        types.ResourceTemplate(
            name=WIDGET.title,
            title=WIDGET.title,
            uriTemplate=WIDGET.template_uri,
            description=_resource_description(),
            mimeType=MIME_TYPE,
            _meta=_tool_meta(),
        )
    ]


async def _handle_read_resource(req: types.ReadResourceRequest) -> types.ServerResult:
    if str(req.params.uri) != WIDGET.template_uri:
        return types.ServerResult(
            types.ReadResourceResult(
                contents=[],
                _meta={"error": f"Unknown resource: {req.params.uri}"},
            )
        )

    contents = [
        types.TextResourceContents(
            uri=WIDGET.template_uri,
            mimeType=MIME_TYPE,
            text=WIDGET.html,
            _meta=_tool_meta(),
        )
    ]

    return types.ServerResult(types.ReadResourceResult(contents=contents))


async def _call_tool_request(req: types.CallToolRequest) -> types.ServerResult:
    if req.params.name != WIDGET.identifier:
        return types.ServerResult(
            types.CallToolResult(
                content=[
                    types.TextContent(
                        type="text",
                        text=f"Unknown tool: {req.params.name}",
                    )
                ],
                isError=True,
            )
        )

    # Extract timer parameters from the request
    args = req.params.arguments or {}
    hours = args.get("hours", 0)
    minutes = args.get("minutes", 0)
    seconds = args.get("seconds", 0)
    message = args.get("message", "")

    widget_resource = _embedded_widget_resource()
    meta: Dict[str, Any] = {
        "openai.com/widget": widget_resource.model_dump(mode="json"),
        "openai/outputTemplate": WIDGET.template_uri,
        "openai/toolInvocation/invoking": WIDGET.invoking,
        "openai/toolInvocation/invoked": WIDGET.invoked,
        "openai/widgetAccessible": True,
        "openai/resultCanProduceWidget": True,
    }

    # Format time for display
    time_parts = []
    if hours > 0:
        time_parts.append(f"{hours} hour{'s' if hours != 1 else ''}")
    if minutes > 0:
        time_parts.append(f"{minutes} minute{'s' if minutes != 1 else ''}")
    if seconds > 0:
        time_parts.append(f"{seconds} second{'s' if seconds != 1 else ''}")

    time_str = ", ".join(time_parts) if time_parts else "0 seconds"

    response_text = f"Timer set for {time_str}"
    if message:
        response_text += f" - {message}"
    response_text += ". Click Start to begin the countdown!"

    return types.ServerResult(
        types.CallToolResult(
            content=[
                types.TextContent(
                    type="text",
                    text=response_text,
                )
            ],
            structuredContent={
                "hours": hours,
                "minutes": minutes,
                "seconds": seconds,
                "message": message,
                "isRunning": False,
                "isPaused": False,
            },
            _meta=meta,
        )
    )


mcp._mcp_server.request_handlers[types.CallToolRequest] = _call_tool_request
mcp._mcp_server.request_handlers[types.ReadResourceRequest] = _handle_read_resource


# NOTE: This main function is for local testing; it spins up the MCP server (SSE) and
# serves the static assets for the web client. You can view the tool results / resources
# in MCP Inspector.
# Client development/testing should be done using the development webserver spun up via `yarn start`
# in the `web/` directory.
async def main():
    async with app.run() as timer_app:
        mcp_server = create_mcp_server_for_app(timer_app)

        ASSETS_DIR = BUILD_DIR / "static"
        if not ASSETS_DIR.exists():
            raise FileNotFoundError(
                f"Assets directory not found at {ASSETS_DIR}. "
                "Please build the web client before running the server."
            )

        starlette_app = mcp_server.sse_app()

        # This serves the static css and js files referenced by the HTML
        starlette_app.routes.append(
            Mount("/static", app=StaticFiles(directory=ASSETS_DIR), name="static")
        )

        # This serves the main HTML file at the root path for the server
        starlette_app.routes.append(
            Mount(
                "/",
                app=StaticFiles(directory=BUILD_DIR, html=True),
                name="root",
            )
        )

        # Serve via uvicorn, mirroring FastMCP.run_sse_async
        config = uvicorn.Config(
            starlette_app,
            host=mcp_server.settings.host,
            port=int(mcp_server.settings.port),
        )
        server = uvicorn.Server(config)
        await server.serve()


if __name__ == "__main__":
    asyncio.run(main())
