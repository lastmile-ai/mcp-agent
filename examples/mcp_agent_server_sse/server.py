from typing import Any

import uvicorn
from mcp import Tool
from mcp.server import Server, InitializationOptions, NotificationOptions
from mcp.server.sse import SseServerTransport
from mcp.types import TextContent, ImageContent, EmbeddedResource
from starlette.applications import Starlette
from starlette.routing import Route, Mount
from starlette.types import Scope, Receive, Send


def main():
    sse_server_transport: SseServerTransport = SseServerTransport("/messages/")
    server: Server = Server("test-service")

    @server.list_tools()
    async def handle_list_tools() -> list[Tool]:
        return [
            Tool(
                name="get-magic-number",
                description="Returns the magic number",
            )
        ]

    @server.call_tool()
    async def handle_call_tool(
            name: str, arguments: dict[str, Any] | None
    ) -> list[TextContent | ImageContent | EmbeddedResource]:
        return await TextContent(
            type="text",
            text="42"
        )

    initialization_options: InitializationOptions = InitializationOptions(
        server_name=server.name,
        server_version="1.0.0",
        capabilities=server.get_capabilities(
            notification_options=NotificationOptions(),
            experimental_capabilities={},
        ),
    )

    async def handle_sse(request):
        async with sse_server_transport.connect_sse(
                scope=request.scope,
                receive=request.receive,
                send=request._send
        ) as streams:
            await server.run(
                read_stream=streams[0],
                write_stream=streams[1],
                initialization_options=initialization_options
            )

    starlette_app: Starlette = Starlette(
        routes=[
            Route("/sse", endpoint=handle_sse),
            Mount("/messages/", app=sse_server_transport.handle_post_message)
        ],
    )

    uvicorn.run(starlette_app, host="0.0.0.0", port=8000, log_level=-10000)


if __name__ == '__main__':
    main()
