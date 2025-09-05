"""Tail logs from deployed MCP apps."""

import asyncio
import json
import re
import signal
import sys
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List
from urllib.parse import urlparse

import httpx
import typer
import yaml
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn

from mcp_agent.cli.exceptions import CLIError
from mcp_agent.cli.auth import load_credentials, UserCredentials
from mcp_agent.cli.core.constants import DEFAULT_API_BASE_URL
from mcp_agent.cli.core.utils import parse_app_identifier, resolve_server_url

console = Console()

DEFAULT_LOG_LIMIT = 100


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
        DEFAULT_LOG_LIMIT,
        "--limit",
        "-n",
        help=f"Maximum number of log entries to show (default: {DEFAULT_LOG_LIMIT})",
    ),
    order_by: Optional[str] = typer.Option(
        None,
        "--order-by",
        help="Field to order by. Options: timestamp, severity (default: timestamp)",
    ),
    asc: bool = typer.Option(
        False,
        "--asc",
        help="Sort in ascending order (oldest first)",
    ),
    desc: bool = typer.Option(
        False,
        "--desc",
        help="Sort in descending order (newest first, default)",
    ),
    format: Optional[str] = typer.Option(
        "text",
        "--format",
        help="Output format. Options: text, json, yaml (default: text)",
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
    
    # Validate conflicting options
    if follow and since:
        console.print("[red]Error: --since cannot be used with --follow (streaming mode)[/red]")
        raise typer.Exit(6)
    
    if follow and limit != DEFAULT_LOG_LIMIT:
        console.print("[red]Error: --limit cannot be used with --follow (streaming mode)[/red]")
        raise typer.Exit(6)
    
    if follow and order_by:
        console.print("[red]Error: --order-by cannot be used with --follow (streaming mode)[/red]")
        raise typer.Exit(6)
    
    if follow and (asc or desc):
        console.print("[red]Error: --asc/--desc cannot be used with --follow (streaming mode)[/red]")
        raise typer.Exit(6)
    
    # Validate order_by values
    if order_by and order_by not in ["timestamp", "severity"]:
        console.print("[red]Error: --order-by must be 'timestamp' or 'severity'[/red]")
        raise typer.Exit(6)
    
    # Validate that both --asc and --desc are not used together
    if asc and desc:
        console.print("[red]Error: Cannot use both --asc and --desc together[/red]")
        raise typer.Exit(6)
    
    # Validate format values
    if format and format not in ["text", "json", "yaml"]:
        console.print("[red]Error: --format must be 'text', 'json', or 'yaml'[/red]")
        raise typer.Exit(6)
    
    app_id, config_id, server_url = parse_app_identifier(app_identifier)
    
    try:
        if follow:
            asyncio.run(_stream_logs(
                app_id=app_id,
                config_id=config_id,
                server_url=server_url,
                credentials=credentials,
                grep_pattern=grep,
                app_identifier=app_identifier,
                format=format,
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
                order_by=order_by,
                asc=asc,
                desc=desc,
                format=format,
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
    order_by: Optional[str],
    asc: bool,
    desc: bool,
    format: str,
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
    
    if order_by:
        if order_by == "timestamp":
            payload["orderBy"] = "LOG_ORDER_BY_TIMESTAMP"
        elif order_by == "severity":
            payload["orderBy"] = "LOG_ORDER_BY_LEVEL"
    
    if asc:
        payload["order"] = "LOG_ORDER_ASC"
    elif desc:
        payload["order"] = "LOG_ORDER_DESC"
    
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
        transient=True,
    ) as progress:
        progress.add_task("Fetching logs...", total=None)
        
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
    
    _display_logs(filtered_logs, title=f"Logs for {app_id or config_id}", format=format)



async def _stream_logs(
    app_id: Optional[str],
    config_id: Optional[str],
    server_url: Optional[str], 
    credentials: UserCredentials,
    grep_pattern: Optional[str],
    app_identifier: str,
    format: str,
) -> None:
    """Stream logs continuously via SSE."""
    
    if not server_url:
        server_url = await resolve_server_url(app_id, config_id, credentials)
    
    parsed = urlparse(server_url)
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
    
    console.print(f"[blue]Streaming logs from {app_identifier} (Press Ctrl+C to stop)[/blue]")
    
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
                            data_content = line.removeprefix('data:')
                            
                            try:
                                log_data = json.loads(data_content)
                                
                                if 'message' in log_data:
                                    timestamp = log_data.get('time')
                                    if timestamp:
                                        formatted_timestamp = _convert_timestamp_to_local(timestamp)
                                    else:
                                        formatted_timestamp = datetime.now().isoformat()
                                    
                                    log_entry = {
                                        'timestamp': formatted_timestamp,
                                        'message': log_data['message'],
                                        'level': log_data.get('level', 'INFO')
                                    }
                                    
                                    if not grep_pattern or _matches_pattern(log_entry['message'], grep_pattern):
                                        _display_log_entry(log_entry, format=format)
                                        
                            except json.JSONDecodeError:
                                # Skip malformed JSON
                                continue
                                
    except httpx.RequestError as e:
        raise CLIError(f"Failed to connect to log stream: {e}")




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


def _clean_log_entry(entry: Dict[str, Any]) -> Dict[str, Any]:
    """Clean up a log entry for structured output formats."""
    cleaned_entry = entry.copy()
    cleaned_entry['severity'] = _parse_log_level(entry.get('level', 'INFO'))
    cleaned_entry['message'] = _clean_message(entry.get('message', ''))
    cleaned_entry.pop('level', None)
    return cleaned_entry


def _display_text_log_entry(entry: Dict[str, Any]) -> None:
    """Display a single log entry in text format."""
    timestamp = _format_timestamp(entry.get('timestamp', ''))
    raw_level = entry.get('level', 'INFO')
    level = _parse_log_level(raw_level)
    message = _clean_message(entry.get('message', ''))
    
    level_style = _get_level_style(level)
    
    console.print(
        f"[bright_black not bold]{timestamp}[/bright_black not bold] "
        f"[{level_style}]{level:7}[/{level_style}] "
        f"{message}"
    )


def _display_logs(log_entries: List[Dict[str, Any]], title: str = "Logs", format: str = "text") -> None:
    """Display logs in the specified format."""
    if not log_entries:
        return
    
    if format == "json":
        cleaned_entries = [_clean_log_entry(entry) for entry in log_entries]
        print(json.dumps(cleaned_entries, indent=2))
    elif format == "yaml":
        cleaned_entries = [_clean_log_entry(entry) for entry in log_entries]
        print(yaml.dump(cleaned_entries, default_flow_style=False))
    else:  # text format (default)
        if title:
            console.print(f"[bold blue]{title}[/bold blue]\n")
        
        for entry in log_entries:
            _display_text_log_entry(entry)


def _display_log_entry(log_entry: Dict[str, Any], format: str = "text") -> None:
    """Display a single log entry for streaming."""
    if format == "json":
        cleaned_entry = _clean_log_entry(log_entry)
        print(json.dumps(cleaned_entry))
    elif format == "yaml":
        cleaned_entry = _clean_log_entry(log_entry)
        print(yaml.dump([cleaned_entry], default_flow_style=False))
    else:  # text format (default)
        _display_text_log_entry(log_entry)


def _convert_timestamp_to_local(timestamp: float) -> str:
    """Convert UTC timestamp to local time ISO format."""
    dt_utc = datetime.fromtimestamp(timestamp, timezone.utc)
    dt_local = dt_utc.astimezone()
    return dt_local.isoformat()


def _format_timestamp(timestamp_str: str) -> str:
    """Format timestamp for display, converting to local time."""
    try:
        if timestamp_str:
            # Parse UTC timestamp and convert to local time
            dt_utc = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
            dt_local = dt_utc.astimezone()
            return dt_local.strftime('%H:%M:%S')
        return datetime.now().strftime('%H:%M:%S')
    except (ValueError, TypeError):
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
