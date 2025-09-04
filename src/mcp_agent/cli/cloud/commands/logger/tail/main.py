"""Tail logs from deployed MCP apps."""

import asyncio
import json
import re
import signal
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Dict, Any, List
from urllib.parse import urlparse

import httpx
import typer
import yaml
from rich.console import Console
from rich.live import Live
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table
from rich.text import Text

from mcp_agent.cli.exceptions import CLIError
from mcp_agent.cli.auth import load_credentials, UserCredentials
from mcp_agent.cli.core.constants import DEFAULT_API_BASE_URL

console = Console()


def tail_logs(
    app_identifier: str = typer.Argument(
        help="Server ID, URL, or app configuration ID to retrieve logs for"
    ),
    since: Optional[str] = typer.Option(
        None,
        "--since",
        help="Show logs from duration ago (e.g., '1h', '30m', '2d')",
    ),
    grep: Optional[str] = typer.Option(
        None,
        "--grep",
        help="Filter log messages matching this pattern (regex supported)",
    ),
    follow: bool = typer.Option(
        False,
        "--follow",
        "-f",
        help="Stream logs continuously",
    ),
    limit: Optional[int] = typer.Option(
        100,
        "--limit",
        "-n",
        help="Maximum number of log entries to show (default: 100)",
    ),
) -> None:
    """Tail logs for an MCP app deployment.
    
    Retrieve and optionally stream logs from deployed MCP apps. Supports filtering
    by time duration, text patterns, and continuous streaming.
    
    Examples:
        # Get last 50 logs from an app
        mcp-agent cloud logger tail app_abc123 --limit 50
        
        # Stream logs continuously
        mcp-agent cloud logger tail https://app.mcpac.dev/abc123 --follow
        
        # Show logs from the last hour with error filtering
        mcp-agent cloud logger tail app_abc123 --since 1h --grep "ERROR|WARN"
        
        # Follow logs and filter for specific patterns
        mcp-agent cloud logger tail app_abc123 --follow --grep "authentication.*failed"
    """
    
    credentials = load_credentials()
    if not credentials:
        console.print("[red]Error: Not authenticated. Run 'mcp-agent login' first.[/red]")
        raise typer.Exit(4)
    
    app_id, config_id, server_url = _parse_app_identifier(app_identifier)
    
    try:
        if follow:
            asyncio.run(_stream_logs(
                app_id=app_id,
                config_id=config_id,
                server_url=server_url,
                credentials=credentials,
                grep_pattern=grep,
            ))
        else:
            asyncio.run(_fetch_logs(
                app_id=app_id,
                config_id=config_id,
                server_url=server_url,
                credentials=credentials,
                since=since,
                grep_pattern=grep,
                limit=limit,
            ))
            
    except KeyboardInterrupt:
        console.print("\n[yellow]Interrupted by user[/yellow]")
        sys.exit(0)
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(5)


async def _fetch_logs(
    app_id: Optional[str],
    config_id: Optional[str], 
    server_url: Optional[str],
    credentials: UserCredentials,
    since: Optional[str],
    grep_pattern: Optional[str],
    limit: int,
) -> None:
    """Fetch logs one-time via HTTP API."""
    
    api_base = DEFAULT_API_BASE_URL
    headers = {
        "Authorization": f"Bearer {credentials.api_key}",
        "Content-Type": "application/json",
    }
    
    payload = {}
    
    if app_id:
        payload["app_id"] = app_id
    elif config_id:
        payload["app_configuration_id"] = config_id
    else:
        raise CLIError("Unable to determine app or configuration ID from provided identifier")
    
    if since:
        payload["since"] = since
    if limit:
        payload["limit"] = limit
    
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
        transient=True,
    ) as progress:
        task = progress.add_task("Fetching logs...", total=None)
        
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    f"{api_base}/mcp_app/get_app_logs",
                    json=payload,
                    headers=headers,
                )
                
                if response.status_code == 401:
                    raise CLIError("Authentication failed. Try running 'mcp-agent login'")
                elif response.status_code == 404:
                    raise CLIError("App or configuration not found")
                elif response.status_code != 200:
                    raise CLIError(f"API request failed: {response.status_code} {response.text}")
                
                data = response.json()
                log_entries = data.get("logEntries", [])
                
        except httpx.RequestError as e:
            raise CLIError(f"Failed to connect to API: {e}")
    
    filtered_logs = _filter_logs(log_entries, grep_pattern) if grep_pattern else log_entries
    
    if not filtered_logs:
        console.print("[yellow]No logs found matching the criteria[/yellow]")
        return
    
    _display_logs(filtered_logs, title=f"Logs for {app_id or config_id}")


async def _resolve_server_url(
    app_id: Optional[str],
    config_id: Optional[str], 
    credentials: UserCredentials,
) -> str:
    """Resolve server URL from app ID or configuration ID."""
    
    api_base = DEFAULT_API_BASE_URL
    headers = {
        "Authorization": f"Bearer {credentials.api_key}",
        "Content-Type": "application/json",
    }
    
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            if app_id:
                response = await client.post(
                    f"{api_base}/mcp_app/get_app",
                    json={"app_id": app_id},
                    headers=headers,
                )
                
                if response.status_code == 404:
                    raise CLIError(f"App '{app_id}' not found")
                elif response.status_code != 200:
                    raise CLIError(f"Failed to get app info: {response.status_code} {response.text}")
                
                data = response.json()
                app_info = data.get("app", {})
                server_info = app_info.get("appServerInfo")
                
                if not server_info:
                    raise CLIError(f"App '{app_id}' is not deployed yet")
                
                server_url = server_info.get("serverUrl")
                if not server_url:
                    raise CLIError(f"No server URL found for app '{app_id}'")
                    
                status = server_info.get("status", "APP_SERVER_STATUS_UNSPECIFIED")
                if status == "APP_SERVER_STATUS_OFFLINE":
                    raise CLIError(f"App '{app_id}' server is offline")
                
                return server_url
                
            elif config_id:
                response = await client.post(
                    f"{api_base}/mcp_app/get_app_configuration",
                    json={"app_configuration_id": config_id},
                    headers=headers,
                )
                
                if response.status_code == 404:
                    raise CLIError(f"App configuration '{config_id}' not found")
                elif response.status_code != 200:
                    raise CLIError(f"Failed to get app configuration: {response.status_code} {response.text}")
                
                data = response.json()
                app_config = data.get("appConfiguration", {})
                server_info = app_config.get("appServerInfo")
                
                if not server_info:
                    raise CLIError(f"App configuration '{config_id}' is not deployed yet")
                
                server_url = server_info.get("serverUrl")
                if not server_url:
                    raise CLIError(f"No server URL found for app configuration '{config_id}'")
                    
                status = server_info.get("status", "APP_SERVER_STATUS_UNSPECIFIED")
                if status == "APP_SERVER_STATUS_OFFLINE":
                    raise CLIError(f"App configuration '{config_id}' server is offline")
                
                return server_url
                
            else:
                raise CLIError("Either app_id or config_id must be provided")
                
    except httpx.RequestError as e:
        raise CLIError(f"Failed to connect to API: {e}")


async def _stream_logs(
    app_id: Optional[str],
    config_id: Optional[str],
    server_url: Optional[str], 
    credentials: UserCredentials,
    grep_pattern: Optional[str],
) -> None:
    """Stream logs continuously via SSE."""
    
    if server_url:
        parsed = urlparse(server_url)
        stream_url = f"{parsed.scheme}://{parsed.netloc}/logs"
        hostname = parsed.hostname or ""
        deployment_id = hostname.split('.')[0] if '.' in hostname else hostname
    else:
        resolved_server_url = await _resolve_server_url(app_id, config_id, credentials)
        parsed = urlparse(resolved_server_url)
        stream_url = f"{parsed.scheme}://{parsed.netloc}/logs"
        hostname = parsed.hostname or ""
        deployment_id = hostname.split('.')[0] if '.' in hostname else hostname
    
    headers = {
        "Accept": "text/event-stream",
        "Cache-Control": "no-cache",
        "X-Routing-Key": deployment_id,
    }
    
    if credentials.api_key:
        headers["Authorization"] = f"Bearer {credentials.api_key}"
    
    console.print(f"[blue]Streaming logs from {stream_url} (Press Ctrl+C to stop)[/blue]")
    
    # Setup signal handler for graceful shutdown
    def signal_handler(signum, frame):
        console.print("\n[yellow]Stopping log stream...[/yellow]")
        sys.exit(0)
    
    signal.signal(signal.SIGINT, signal_handler)
    
    try:
        async with httpx.AsyncClient(timeout=None) as client:
            async with client.stream("GET", stream_url, headers=headers) as response:
                
                if response.status_code == 401:
                    raise CLIError("Authentication failed. Try running 'mcp-agent login'")
                elif response.status_code == 404:
                    raise CLIError("Log stream not found for the specified app")
                elif response.status_code != 200:
                    raise CLIError(f"Failed to connect to log stream: {response.status_code}")
                
                console.print("[green]✓ Connected to log stream[/green]\n")
                
                buffer = ""
                async for chunk in response.aiter_text():
                    buffer += chunk
                    lines = buffer.split('\n')
                    
                    for line in lines[:-1]:
                        if line.startswith('data:'):
                            
                            if data_content.strip() == '[DONE]':
                                continue
                            
                            try:
                                log_data = json.loads(data_content)
                                
                                if 'message' in log_data:
                                    timestamp = log_data.get('time')
                                    if timestamp:
                                        dt = datetime.fromtimestamp(timestamp, timezone.utc)
                                        formatted_timestamp = dt.isoformat()
                                    else:
                                        formatted_timestamp = datetime.now(timezone.utc).isoformat()
                                    
                                    log_entry = {
                                        'timestamp': formatted_timestamp,
                                        'message': log_data['message'],
                                        'level': log_data.get('level', 'INFO')
                                    }
                                    
                                    if not grep_pattern or _matches_pattern(log_entry['message'], grep_pattern):
                                        _display_log_entry(log_entry)
                                        
                            except json.JSONDecodeError:
                                # Skip malformed JSON
                                continue
                                
    except httpx.RequestError as e:
        raise CLIError(f"Failed to connect to log stream: {e}")


def _parse_app_identifier(identifier: str) -> tuple[Optional[str], Optional[str], Optional[str]]:
    """Parse app identifier to extract app ID, config ID, and server URL."""
    
    if identifier.startswith(('http://', 'https://')):
        return None, None, identifier
    if identifier.startswith('apcnf_'):
        return None, identifier, None
    if identifier.startswith('app_'):
        return identifier, None, None
    
    return identifier, None, None


def _filter_logs(log_entries: List[Dict[str, Any]], pattern: str) -> List[Dict[str, Any]]:
    """Filter log entries by pattern."""
    if not pattern:
        return log_entries
    
    try:
        regex = re.compile(pattern, re.IGNORECASE)
        return [entry for entry in log_entries if regex.search(entry.get('message', ''))]
    except re.error:
        return [entry for entry in log_entries if pattern.lower() in entry.get('message', '').lower()]


def _matches_pattern(message: str, pattern: str) -> bool:
    """Check if message matches the pattern."""
    try:
        regex = re.compile(pattern, re.IGNORECASE)
        return bool(regex.search(message))
    except re.error:
        return pattern.lower() in message.lower()


def _display_logs(log_entries: List[Dict[str, Any]], title: str = "Logs") -> None:
    """Display logs in inline format."""
    if not log_entries:
        return
    
    if title:
        console.print(f"[bold blue]{title}[/bold blue]\n")
    
    for entry in log_entries:
        timestamp = _format_timestamp(entry.get('timestamp', ''))
        raw_level = entry.get('level', 'INFO')
        level = _parse_log_level(raw_level)
        message = _clean_message(entry.get('message', ''))

        level_style = _get_level_style(level)
        
        # Format: [timestamp] LEVEL message
        console.print(
            f"[bright_black not bold]{timestamp}[/bright_black not bold] "
            f"[{level_style}]{level:5}[/{level_style}] "
            f"{message}"
        )


def _display_log_entry(log_entry: Dict[str, Any]) -> None:
    """Display a single log entry for streaming."""
    timestamp = _format_timestamp(log_entry.get('timestamp', ''))
    raw_level = log_entry.get('level', 'INFO')
    level = _parse_log_level(raw_level)
    message = _clean_message(log_entry.get('message', ''))
    
    level_style = _get_level_style(level)
    
    console.print(
        f"[bright_black not bold]{timestamp}[/bright_black not bold] "
        f"[{level_style}]{level:5}[/{level_style}] "
        f"{message}"
    )


def _format_timestamp(timestamp_str: str) -> str:
    """Format timestamp for display."""
    try:
        if timestamp_str:
            dt = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
            return dt.strftime('%H:%M:%S')
        return datetime.now().strftime('%H:%M:%S')
    except:
        return timestamp_str[:8] if len(timestamp_str) >= 8 else timestamp_str


def _parse_log_level(level: str) -> str:
    """Parse log level from API format to clean display format."""
    if level.startswith('LOG_LEVEL_'):
        clean_level = level.replace('LOG_LEVEL_', '')
        if clean_level == 'UNSPECIFIED':
            return 'UNKNOWN'
        return clean_level
    return level.upper()


def _clean_message(message: str) -> str:
    """Remove redundant log level prefix from message if present."""
    prefixes = [
        'ERROR:', 'WARNING:', 'INFO:', 'DEBUG:', 'TRACE:',
        'WARN:', 'FATAL:', 'UNKNOWN:', 'UNSPECIFIED:'
    ]
    
    for prefix in prefixes:
        if message.startswith(prefix):
            return message[len(prefix):].lstrip()
    
    return message


def _get_level_style(level: str) -> str:
    """Get Rich style for log level."""
    level = level.upper()
    if level in ['ERROR', 'FATAL']:
        return "red bold"
    elif level in ['WARN', 'WARNING']:
        return "yellow bold"
    elif level == 'INFO':
        return "blue"
    elif level in ['DEBUG', 'TRACE']:
        return "dim"
    elif level in ['UNKNOWN', 'UNSPECIFIED']:
        return "magenta"
    else:
        return "white"


def _truncate_message(message: str, max_length: int = 100) -> str:
    """Truncate long messages for table display."""
    if len(message) <= max_length:
        return message
    return message[:max_length-3] + "..."