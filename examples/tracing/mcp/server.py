from typing import Any

import uvicorn
from mcp import Tool
from mcp.server import InitializationOptions, NotificationOptions, Server
from mcp.server.sse import SseServerTransport
from mcp.types import EmbeddedResource, ImageContent, TextContent
from openinference.instrumentation.mcp import MCPInstrumentor
from opentelemetry import trace
from starlette.applications import Starlette
from starlette.routing import Mount, Route

from mcp_agent.tracing.semconv import GEN_AI_TOOL_NAME
from mcp_agent.tracing.telemetry import record_attributes, telemetry


def _configure_server_otel():
    """
    Configure OpenTelemetry for the MCP server.
    This function sets up the global textmap propagator and initializes the tracer provider.
    """
    MCPInstrumentor().instrument()


def get_magic_number(original_number: int = 0) -> int:
    tracer = trace.get_tracer(__name__)
    with tracer.start_as_current_span("some_tool_function") as span:
        span.set_attribute("example.attribute", "value")
        result = 42 + original_number
        span.set_attribute("result", result)
        return result


def main():
    sse_server_transport: SseServerTransport = SseServerTransport("/messages/")
    server: Server = Server("test-service")

    @server.list_tools()
    @telemetry.traced(kind=trace.SpanKind.SERVER)
    async def handle_list_tools() -> list[Tool]:
        return [
            Tool(
                name="get-magic-number",
                description="Returns a magic number",
                inputSchema={
                    "type": "object",
                    "properties": {"original_number": {"type": "number"}},
                },
            )
        ]

    @server.call_tool()
    @telemetry.traced(kind=trace.SpanKind.SERVER)
    async def handle_call_tool(
        name: str, arguments: dict[str, Any] | None
    ) -> list[TextContent | ImageContent | EmbeddedResource]:
        span = trace.get_current_span()
        res = str(get_magic_number(arguments.get("original_number", 0)))
        span.set_attribute(GEN_AI_TOOL_NAME, name)
        span.set_attribute("result", res)
        if arguments:
            record_attributes(span, arguments, "arguments")

        return [
            TextContent(type="text", text=res)
        ]  # Return a list, not awaiting the content

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
            scope=request.scope, receive=request.receive, send=request._send
        ) as streams:
            await server.run(
                read_stream=streams[0],
                write_stream=streams[1],
                initialization_options=initialization_options,
            )

    starlette_app: Starlette = Starlette(
        routes=[
            Route("/sse", endpoint=handle_sse),
            Mount("/messages/", app=sse_server_transport.handle_post_message),
        ],
    )

    uvicorn.run(starlette_app, host="0.0.0.0", port=8000, log_level=-10000)


if __name__ == "__main__":
    _configure_server_otel()
    main()
