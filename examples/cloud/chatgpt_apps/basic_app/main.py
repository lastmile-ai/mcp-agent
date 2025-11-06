"""Basic MCP mcp-agent app integration with OpenAI Apps SDK.

The server exposes widget-backed tools that render the UI bundle within the
client directory. Each handler returns the HTML shell via an MCP resource and
returns structured content so the ChatGPT client can hydrate the widget."""

import asyncio
from dataclasses import dataclass
from pathlib import Path
from random import choice
from typing import Any, Dict

import mcp.types as types
import uvicorn
from mcp.server.fastmcp import FastMCP
from starlette.routing import Mount
from starlette.staticfiles import StaticFiles

from mcp_agent.app import MCPApp
from mcp_agent.server.app_server import create_mcp_server_for_app


@dataclass(frozen=True)
class CoinFlipWidget:
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
JS_PATH = ASSETS_DIR / "js" / "main.9c62c88b.js"
CSS_PATH = ASSETS_DIR / "css" / "main.57005a98.css"


# METHOD 1: Inline the JS and CSS into the HTML template
COIN_FLIP_JS = JS_PATH.read_text(encoding="utf-8")
COIN_FLIP_CSS = CSS_PATH.read_text(encoding="utf-8")

INLINE_HTML_TEMPLATE = f"""
<div id="coinflip-root"></div>
<style>
{COIN_FLIP_CSS}
</style>
<script type="module">
{COIN_FLIP_JS}
</script>
"""

# METHOD 2: Reference the static files from the deployed server
SERVER_URL = "https://<server_id>.deployments.mcp-agent.com"  # e.g. "https://15da9n6bk2nj3wiwf7ghxc2fy7sc6c8a.deployments.mcp-agent.com"
DEPLOYED_HTML_TEMPLATE = (
    '<div id="coinflip-root"></div>\n'
    f'<link rel="stylesheet" href="{SERVER_URL}/static/css/main.57005a98.css">\n'
    f'<script type="module" src="{SERVER_URL}/static/js/main.9c62c88b.js"></script>'
)


WIDGET = CoinFlipWidget(
    identifier="coin-flip",
    title="Flip a Coin",
    # OpenAI Apps heavily cache resource by URI, so use a date-based URI to bust the cache when updating the app.
    template_uri="ui://widget/coin-flip-10-27-2025-16-34.html",
    invoking="Preparing for coin flip",
    invoked="Flipping the coin...",
    html=INLINE_HTML_TEMPLATE,  # Use INLINE_HTML_TEMPLATE or DEPLOYED_HTML_TEMPLATE
    response_text="Flipped the coin! Click the coin to flip again.",
)


MIME_TYPE = "text/html+skybridge"

mcp = FastMCP(
    name="coinflip",
    stateless_http=True,
)
app = MCPApp(
    name="coinflip", description="UX for flipping a coin within an OpenAI chat", mcp=mcp
)


def _resource_description() -> str:
    return "Coin flip widget markup"


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


def _tool_meta() -> Dict[str, Any]:
    return {
        "openai.com/widget": _embedded_widget_resource().model_dump(mode="json"),
        "openai/outputTemplate": WIDGET.template_uri,
        "openai/toolInvocation/invoking": WIDGET.invoking,
        "openai/toolInvocation/invoked": WIDGET.invoked,
        "openai/widgetAccessible": True,
        "openai/resultCanProduceWidget": True,
    }


@app.tool(
    name=WIDGET.identifier,
    title=WIDGET.title,
    description="Flip a coin and get heads or tails.",
    annotations=types.ToolAnnotations(
        destructiveHint=False,
        openWorldHint=False,
        readOnlyHint=True,
    ),
    structured_output=True,
    meta=_tool_meta(),
)
async def flip_coin() -> Dict[str, str]:
    """Flip a coin and get heads or tails."""
    flip_result = choice(["heads", "tails"])
    return {"flipResult": flip_result}


@mcp.resource(
    uri=WIDGET.template_uri,
    title=WIDGET.title,
    description=_resource_description(),
    mime_type=MIME_TYPE,
)
def get_widget_html() -> str:
    """Provide the HTML template for the coin flip widget."""
    return WIDGET.html


# NOTE: This main function is for local testing; it spins up the MCP server (SSE) and
# serves the static assets for the web client. You can view the tool results / resources
# in MCP Inspector.
# Client development/testing should be done using the development webserver spun up via `yarn start`
# in the `web/` directory.
async def main():
    async with app.run() as coinflip_app:
        mcp_server = create_mcp_server_for_app(coinflip_app)

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
