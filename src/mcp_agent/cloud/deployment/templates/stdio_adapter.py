"""
Adapter for running STDIO-based servers as HTTP servers.

This script acts as a bridge between HTTP requests and a STDIO-based server.
It starts the STDIO server as a subprocess, forwards requests to it via stdin,
and returns responses from stdout.
"""

import asyncio
import json
import logging
import os
import signal
import sys
from typing import Optional, Tuple, Dict, Any, List

from aiohttp import web

# Configure logging
LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO").upper()
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL),
    format='%(asctime)s [stdio_adapter] %(levelname)-8s: %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
    stream=sys.stdout
)
logger = logging.getLogger("stdio_adapter")


class StdioProcess:
    """
    Manages communication with a STDIO-based process.
    
    This class handles starting the subprocess, writing to its stdin,
    reading from its stdout, and monitoring its stderr.
    """
    
    def __init__(self, cmd: List[str]):
        """
        Initialize the STDIO process.
        
        Args:
            cmd: Command to run the process
        """
        self.cmd = cmd
        self.process = None
        self.stdout_reader_task = None
        self.stderr_reader_task = None
    
    async def start(self):
        """Start the subprocess and set up communication channels."""
        logger.info(f"Starting STDIO process: {' '.join(self.cmd)}")
        
        # Start the process
        self.process = await asyncio.create_subprocess_exec(
            *self.cmd,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        
        # Start reading stderr in the background
        self.stderr_reader_task = asyncio.create_task(self._read_stderr())
        
        logger.info("STDIO process started")
    
    async def _read_stderr(self):
        """Read and log stderr output from the subprocess."""
        assert self.process is not None
        
        while True:
            try:
                # Use asyncio.wait_for to prevent blocking indefinitely
                line = await asyncio.wait_for(self.process.stderr.readline(), timeout=10.0)
                if not line:
                    logger.info("STDIO process stderr closed")
                    break
                
                # Log stderr (limit size to prevent excessive logging)
                stderr_line = line.decode('utf-8', errors='replace').rstrip()
                if len(stderr_line) > 1000:
                    stderr_line = stderr_line[:997] + "..."
                logger.info(f"[STDIO Server stderr] {stderr_line}")
            except asyncio.TimeoutError:
                # If we timeout, check if process is still running
                if self.process.returncode is not None:
                    logger.info("STDIO process has terminated, stopping stderr reader")
                    break
                logger.debug("Timeout waiting for stderr output, process still running")
            except Exception as e:
                logger.error(f"Error reading stderr: {e}")
                break
    
    async def is_alive(self) -> bool:
        """
        Check if the process is still running.
        
        Returns:
            True if the process is running, False otherwise
        """
        if self.process is None:
            return False
        
        return self.process.returncode is None
    
    async def call(self, method: str, params: Dict[str, Any]) -> Tuple[bool, Any]:
        """
        Call a method on the STDIO process.
        
        Args:
            method: Method name
            params: Method parameters
            
        Returns:
            Tuple of (success, result or error)
        """
        if not await self.is_alive():
            return False, "Process is not running"
        
        # Create request
        request = {
            "method": method,
            "params": params
        }
        
        try:
            # Write to stdin
            request_str = json.dumps(request) + "\n"
            self.process.stdin.write(request_str.encode('utf-8'))
            await self.process.stdin.drain()
            
            # Read from stdout
            response_line = await self.process.stdout.readline()
            if not response_line:
                return False, "Process closed stdout"
            
            # Parse response
            response_str = response_line.decode('utf-8', errors='replace')
            response = json.loads(response_str)
            
            # Check for error
            if response.get("error"):
                return False, response.get("error")
            
            # Return result
            return True, response.get("result")
        except BrokenPipeError:
            return False, "Broken pipe"
        except ConnectionResetError:
            return False, "Connection reset"
        except json.JSONDecodeError as e:
            return False, f"Invalid JSON response: {e}"
        except Exception as e:
            return False, f"Unexpected error: {e}"
    
    async def stop(self):
        """Stop the subprocess and clean up resources."""
        logger.info("Stopping STDIO process")
        
        if self.process is not None:
            # Close stdin
            if self.process.stdin:
                try:
                    self.process.stdin.close()
                except Exception as e:
                    logger.error(f"Error closing stdin: {e}")
            
            # Terminate process
            try:
                self.process.terminate()
                try:
                    await asyncio.wait_for(self.process.wait(), timeout=5.0)
                    logger.info("Process terminated gracefully")
                except asyncio.TimeoutError:
                    logger.warning("Process did not terminate within timeout, killing")
                    self.process.kill()
                    try:
                        # Wait for kill to take effect
                        await asyncio.wait_for(self.process.wait(), timeout=2.0)
                        logger.info("Process killed")
                    except asyncio.TimeoutError:
                        logger.error("Process couldn't be killed, might be zombie")
                    except Exception as e:
                        logger.error(f"Error waiting for killed process: {e}")
            except ProcessLookupError:
                logger.info("Process already terminated")
            except Exception as e:
                logger.error(f"Error terminating process: {e}")
        
        # Cancel stderr reader task
        if self.stderr_reader_task is not None:
            self.stderr_reader_task.cancel()
            try:
                await asyncio.wait_for(self.stderr_reader_task, timeout=2.0)
            except asyncio.TimeoutError:
                logger.warning("Timed out waiting for stderr reader task to cancel")
            except asyncio.CancelledError:
                logger.debug("Stderr reader task cancelled successfully")
            except Exception as e:
                logger.error(f"Error cancelling stderr reader task: {e}")
        
        logger.info("STDIO process stopped")


class StdioAdapter:
    """
    Adapter for translating HTTP requests to STDIO calls.
    
    This class serves as a bridge between HTTP requests and a STDIO process,
    exposing the process as a web server.
    """
    
    def __init__(self, cmd: List[str], port: int, api_key: Optional[str] = None):
        """
        Initialize the adapter.
        
        Args:
            cmd: Command to run the STDIO process
            port: Port to listen on
            api_key: Optional API key for authentication
        """
        self.cmd = cmd
        self.port = port
        self.api_key = api_key
        self.process = StdioProcess(cmd)
    
    async def start(self):
        """Start the STDIO process and HTTP server."""
        # Start the STDIO process
        await self.process.start()
        
        # Create the web application
        app = web.Application(middlewares=[self._auth_middleware])
        
        # Set up routes
        app.add_routes([
            web.get("/health", self.handle_health),
            web.post("/mcp/call", self.handle_call),
        ])
        
        # Start the web server
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, "0.0.0.0", self.port)
        await site.start()
        
        logger.info(f"HTTP server listening on 0.0.0.0:{self.port}")
        
        # Keep the server running
        try:
            while True:
                # Check if the process is still alive
                if not await self.process.is_alive():
                    logger.error("STDIO process died, shutting down")
                    break
                
                await asyncio.sleep(1)
        finally:
            # Stop the process and server
            await self.process.stop()
            await runner.cleanup()
    
    @web.middleware
    async def _auth_middleware(self, request, handler):
        """
        Middleware for API key authentication.
        
        Args:
            request: The HTTP request
            handler: The request handler
            
        Returns:
            The response from the handler or 401 Unauthorized
        """
        # Skip authentication for health check
        if request.path == "/health":
            return await handler(request)
        
        # Skip authentication if no API key is configured
        if not self.api_key:
            return await handler(request)
        
        # Get the API key from the Authorization header
        auth_header = request.headers.get("Authorization")
        if not auth_header or not auth_header.startswith("Bearer "):
            return web.json_response(
                {"error": "Missing or invalid Authorization header"},
                status=401
            )
        
        # Extract the token
        token = auth_header[7:]  # Remove "Bearer " prefix
        
        # Check if the token is valid
        if token != self.api_key:
            return web.json_response(
                {"error": "Invalid API key"},
                status=401
            )
        
        # Token is valid, proceed with the request
        return await handler(request)
    
    async def handle_health(self, request: web.Request) -> web.Response:
        """
        Handle health check requests.
        
        Args:
            request: The HTTP request
            
        Returns:
            HTTP 200 OK if the process is alive, 503 Service Unavailable otherwise
        """
        # Check if the process is alive
        if await self.process.is_alive():
            return web.json_response({"status": "ok"})
        else:
            return web.json_response(
                {"status": "error", "message": "STDIO process is not running"},
                status=503
            )
    
    async def handle_call(self, request: web.Request) -> web.Response:
        """
        Handle MCP call requests.
        
        Args:
            request: The HTTP request
            
        Returns:
            HTTP response with the result from the STDIO process
        """
        # Check if the process is alive
        if not await self.process.is_alive():
            return web.json_response(
                {"error": "STDIO process is not running"},
                status=503
            )
        
        try:
            # Parse request body
            try:
                body = await request.json()
            except json.JSONDecodeError:
                return web.json_response(
                    {"error": "Invalid JSON in request body"},
                    status=400
                )
            
            # Extract method and params
            method = body.get("method")
            params = body.get("params", {})
            
            if not method:
                return web.json_response(
                    {"error": "Missing 'method' field in request body"},
                    status=400
                )
            
            # Call the STDIO process
            success, result = await self.process.call(method, params)
            
            if success:
                return web.json_response({"result": result})
            else:
                return web.json_response(
                    {"error": result},
                    status=500
                )
        except Exception as e:
            logger.error(f"Error handling call: {e}")
            return web.json_response(
                {"error": f"Unexpected error: {e}"},
                status=500
            )


def parse_command(command_str: str) -> List[str]:
    """
    Parse a command string into a list of command parts.
    
    Args:
        command_str: Command string in JSON format
        
    Returns:
        List of command parts
    """
    try:
        cmd = json.loads(command_str)
        if not isinstance(cmd, list):
            raise ValueError("Command must be a list of strings")
        
        return cmd
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON in command: {e}")


def handle_signal(signum, frame):
    """
    Handle termination signals for graceful shutdown.
    
    Args:
        signum: Signal number
        frame: Current stack frame
    """
    signal_name = {
        signal.SIGINT: "SIGINT",
        signal.SIGTERM: "SIGTERM"
    }.get(signum, f"signal {signum}")
    
    logger.info(f"Received {signal_name}, initiating graceful shutdown...")
    # System exit will trigger cleanup in the main function
    sys.exit(0)


def main():
    """
    Main entry point for the adapter.
    
    Reads configuration from environment variables and starts the adapter.
    """
    # Setup signal handlers for graceful shutdown
    try:
        signal.signal(signal.SIGINT, handle_signal)
        signal.signal(signal.SIGTERM, handle_signal)
        logger.debug("Signal handlers registered for graceful shutdown")
    except Exception as e:
        logger.warning(f"Failed to set up signal handlers: {e}")
    
    # Read configuration from environment variables
    port_str = os.environ.get("PORT")
    server_command_str = os.environ.get("SERVER_COMMAND")
    api_key = os.environ.get("MCP_SERVER_API_KEY")
    
    # Validate configuration
    if not port_str:
        logger.critical("PORT environment variable not set")
        return 1
    
    if not server_command_str:
        logger.critical("SERVER_COMMAND environment variable not set")
        return 1
    
    try:
        port = int(port_str)
    except ValueError:
        logger.critical(f"Invalid PORT: {port_str}")
        return 1
    
    try:
        cmd = parse_command(server_command_str)
    except ValueError as e:
        logger.critical(f"Invalid SERVER_COMMAND: {e}")
        return 1
    
    # Create and start the adapter
    adapter = StdioAdapter(cmd, port, api_key)
    
    # Run the adapter
    asyncio.run(adapter.start())
    
    return 0


if __name__ == "__main__":
    sys.exit(main())