"""
Custom implementation of stdio_client that handles stderr through rich console.
"""

from contextlib import asynccontextmanager
import subprocess
import anyio
from anyio.streams.text import TextReceiveStream
from mcp.client.stdio import StdioServerParameters, get_default_environment
import mcp.types as types
from mcp_agent.logging.logger import get_logger

logger = get_logger(__name__)


@asynccontextmanager
async def stdio_client_with_rich_stderr(server: StdioServerParameters):
    """
    Modified version of stdio_client that captures stderr and routes it through our rich console.
    Follows the original pattern closely for reliability.

    Args:
        server: The server parameters for the stdio connection
    """
    read_stream_writer, read_stream = anyio.create_memory_object_stream(0)
    write_stream, write_stream_reader = anyio.create_memory_object_stream(0)

    # Open process with stderr piped for capture
    process = await anyio.open_process(
        [server.command, *server.args],
        env=server.env if server.env is not None else get_default_environment(),
        stderr=subprocess.PIPE,
    )

    if process.pid:
        logger.debug(f"Started process '{server.command}' with PID: {process.pid}")

    if process.returncode is not None:
        logger.debug(f"return code (early){process.returncode}")
        raise RuntimeError(
            f"Process terminated immediately with code {process.returncode}"
        )

    async def stdout_reader():
        assert process.stdout, "Opened process is missing stdout"
        try:
            async with read_stream_writer:
                buffer = ""
                async for chunk in TextReceiveStream(
                    process.stdout,
                    encoding=server.encoding,
                    errors=server.encoding_error_handler,
                ):
                    lines = (buffer + chunk).split("\n")
                    buffer = lines.pop()

                    for line in lines:
                        if not line:
                            continue
                        try:
                            message = types.JSONRPCMessage.model_validate_json(line)
                        except Exception as exc:
                            await read_stream_writer.send(exc)
                            continue

                        await read_stream_writer.send(message)
        except anyio.ClosedResourceError:
            await anyio.lowlevel.checkpoint()

    async def stderr_reader():
        assert process.stderr, "Opened process is missing stderr"
        try:
            async for chunk in TextReceiveStream(
                process.stderr,
                encoding=server.encoding,
                errors=server.encoding_error_handler,
            ):
                if chunk.strip():
                    # Let the logging system handle the formatting consistently
                    logger.event("info", "mcpserver.stderr", chunk.rstrip(), None, {})
        except anyio.ClosedResourceError:
            await anyio.lowlevel.checkpoint()

    async def stdin_writer():
        assert process.stdin, "Opened process is missing stdin"
        try:
            async with write_stream_reader:
                async for message in write_stream_reader:
                    json = message.model_dump_json(by_alias=True, exclude_none=True)
                    await process.stdin.send(
                        (json + "\n").encode(
                            encoding=server.encoding,
                            errors=server.encoding_error_handler,
                        )
                    )
        except anyio.ClosedResourceError:
            await anyio.lowlevel.checkpoint()

    # Use context managers to handle cleanup automatically
    async with anyio.create_task_group() as tg, process:
        tg.start_soon(stdout_reader)
        tg.start_soon(stdin_writer)
        tg.start_soon(stderr_reader)
        yield read_stream, write_stream
