"""
Local logs tailing with basic filters.
Resolves log file from Settings.logger.path or path_settings pattern.
"""

from __future__ import annotations

from pathlib import Path
import re
import glob
import json
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Tuple

import typer
from rich.console import Console
from mcp_agent.config import get_settings


app = typer.Typer(help="Tail local logs")
console = Console()


def _resolve_log_file(explicit: Path | None) -> Path | None:
    if explicit:
        return explicit if explicit.exists() else None
    cfg = get_settings()
    if cfg.logger and cfg.logger.path:
        p = Path(cfg.logger.path)
        if p.exists():
            return p
    # Try resolving pattern
    try:
        if (
            cfg.logger
            and cfg.logger.path_settings
            and cfg.logger.path_settings.path_pattern
        ):
            pattern = cfg.logger.path_settings.path_pattern.replace("{unique_id}", "*")
            paths = glob.glob(pattern)
            if paths:
                paths = sorted(
                    paths, key=lambda p: Path(p).stat().st_mtime, reverse=True
                )
                return Path(paths[0])
    except Exception:
        pass
    return None


def _parse_rfc3339(ts: str) -> datetime | None:
    try:
        # Support trailing Z
        if ts.endswith("Z"):
            ts = ts[:-1] + "+00:00"
        return datetime.fromisoformat(ts)
    except Exception:
        return None


def _parse_duration(s: str) -> timedelta | None:
    if not s:
        return None
    try:
        s = s.strip().lower()
        # Support composite like 1h30m (optional)
        total = 0.0
        num = ""
        for ch in s:
            if ch.isdigit() or ch == ".":
                num += ch
                continue
            if not num:
                return None
            val = float(num)
            if ch == "s":
                total += val
            elif ch == "m":
                total += val * 60
            elif ch == "h":
                total += val * 3600
            elif ch == "d":
                total += val * 86400
            elif ch == "w":
                total += val * 604800
            else:
                return None
            num = ""
        if num:
            # Bare number defaults to seconds
            total += float(num)
        return timedelta(seconds=total)
    except Exception:
        return None


def _level_value(level: str | None) -> int:
    if not level:
        return 0
    lvl = str(level).upper()
    mapping = {"DEBUG": 10, "INFO": 20, "WARNING": 30, "ERROR": 40}
    return mapping.get(lvl, 0)


def _extract_tokens(data: Any) -> int:
    """Best-effort token count extractor from a log entry's data field.

    Looks for common keys like total_tokens, tokens, input_tokens+output_tokens, or nested fields.
    """

    def from_dict(d: Dict[str, Any]) -> int:
        # Direct fields
        if "total_tokens" in d and isinstance(d["total_tokens"], (int, float)):
            return int(d["total_tokens"])
        if "tokens" in d and isinstance(d["tokens"], (int, float)):
            return int(d["tokens"])
        # Sum input/output if present
        it = d.get("input_tokens")
        ot = d.get("output_tokens")
        if isinstance(it, (int, float)) or isinstance(ot, (int, float)):
            return int((it or 0) + (ot or 0))
        # Nested common containers
        for key in ("usage", "total_usage", "token_usage", "summary"):
            v = d.get(key)
            if isinstance(v, dict):
                val = from_dict(v)
                if val:
                    return val
        return 0

    try:
        if isinstance(data, dict):
            return from_dict(data)
        return 0
    except Exception:
        return 0


def _filter_time(
    entry_ts: datetime | None,
    since_dt: datetime | None,
    from_dt: datetime | None,
    to_dt: datetime | None,
) -> bool:
    if entry_ts is None:
        # If no timestamp, keep unless strict window specified (stay permissive)
        return True
    if since_dt and entry_ts < since_dt:
        return False
    if from_dt and entry_ts < from_dt:
        return False
    if to_dt and entry_ts > to_dt:
        return False
    return True


@app.callback(invoke_without_command=True)
def logs(
    file: Path = typer.Option(Path(""), "--file"),
    follow: bool = typer.Option(False, "--follow"),
    limit: int = typer.Option(200, "--limit"),
    grep: str | None = typer.Option(None, "--grep"),
    desc: bool = typer.Option(True, "--desc/--asc"),
    since: str | None = typer.Option(
        None, "--since", help="Relative window (e.g., 1h, 30m, 7d)"
    ),
    from_time: str | None = typer.Option(None, "--from", help="RFC3339 start time"),
    to_time: str | None = typer.Option(None, "--to", help="RFC3339 end time"),
    orderby: str = typer.Option(
        "time", "--orderby", help="Sort by: time|severity|tokens"
    ),
) -> None:
    """Tail local logs with filtering and sorting (time/severity/tokens)."""
    resolved = _resolve_log_file(file if str(file) else None)
    if not resolved:
        typer.secho("No log file found", err=True, fg=typer.colors.RED)
        raise typer.Exit(2)
    try:
        # Parse time window boundaries
        now = datetime.now(timezone.utc)
        since_dt = None
        if since:
            delta = _parse_duration(since)
            if delta:
                since_dt = now - delta
        from_dt = _parse_rfc3339(from_time) if from_time else None
        to_dt = _parse_rfc3339(to_time) if to_time else None

        # Normalize to aware UTC if naive
        def _norm(dt: datetime | None) -> datetime | None:
            if not dt:
                return None
            if dt.tzinfo is None:
                return dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc)

        since_dt = _norm(since_dt)
        from_dt = _norm(from_dt)
        to_dt = _norm(to_dt)

        raw_lines = resolved.read_text(encoding="utf-8").splitlines()
        if grep:
            rx = re.compile(grep)
            raw_lines = [ln for ln in raw_lines if rx.search(ln)]

        entries: List[Tuple[Dict[str, Any] | None, str]] = []
        for ln in raw_lines:
            obj = None
            if ln and ln[0] == "{":
                try:
                    obj = json.loads(ln)
                except Exception:
                    obj = None
            entries.append((obj, ln))

        # Apply time filters where possible; keep non-JSON lines permissively
        filtered: List[
            Tuple[Dict[str, Any] | None, str, datetime | None, int, int]
        ] = []
        for obj, ln in entries:
            ts = None
            lvl = 0
            toks = 0
            if isinstance(obj, dict):
                # timestamp
                ts_raw = obj.get("timestamp") or (obj.get("data", {}) or {}).get(
                    "timestamp"
                )
                if isinstance(ts_raw, str):
                    ts = _parse_rfc3339(ts_raw)
                    if ts and ts.tzinfo is None:
                        ts = ts.replace(tzinfo=timezone.utc)
                # level
                lvl = _level_value(obj.get("level"))
                # tokens
                toks = _extract_tokens(obj.get("data"))
            if _filter_time(ts, since_dt, from_dt, to_dt):
                filtered.append((obj, ln, ts, lvl, toks))

        key = orderby.strip().lower() if orderby else "time"
        if key not in ("time", "severity", "tokens"):
            key = "time"

        def sort_key(item):
            _obj, _ln, ts, lvl, toks = item
            if key == "severity":
                return lvl
            if key == "tokens":
                return toks
            # default time
            # None timestamps sort as oldest
            return ts or datetime.fromtimestamp(0, tz=timezone.utc)

        sorted_entries = sorted(filtered, key=sort_key, reverse=desc)
        if limit > 0:
            sorted_entries = sorted_entries[:limit]

        for _obj, ln, *_ in sorted_entries:
            console.print(ln)

        if follow:
            import time

            console.print("Following... (Ctrl+C to stop)")
            with resolved.open("r", encoding="utf-8") as f:
                f.seek(0, 2)
                try:
                    while True:
                        line = f.readline()
                        if not line:
                            time.sleep(0.5)
                            continue
                        if grep and not re.search(grep, line):
                            continue
                        obj = None
                        if line and line[0] == "{":
                            try:
                                obj = json.loads(line)
                            except Exception:
                                obj = None
                        ts = None
                        if isinstance(obj, dict):
                            ts_raw = obj.get("timestamp") or (
                                obj.get("data", {}) or {}
                            ).get("timestamp")
                            if isinstance(ts_raw, str):
                                ts = _parse_rfc3339(ts_raw)
                                if ts and ts.tzinfo is None:
                                    ts = ts.replace(tzinfo=timezone.utc)
                        if not _filter_time(ts, since_dt, from_dt, to_dt):
                            continue
                        console.print(line.rstrip("\n"))
                except KeyboardInterrupt:
                    pass
    except Exception as e:
        typer.secho(f"Error reading logs: {e}", err=True, fg=typer.colors.RED)
        raise typer.Exit(5)
