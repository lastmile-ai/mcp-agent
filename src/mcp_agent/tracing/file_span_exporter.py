from datetime import datetime
from os import linesep
from pathlib import Path
from typing import Callable, Sequence
import uuid

from opentelemetry.sdk.trace import ReadableSpan
from opentelemetry.sdk.trace.export import SpanExporter, SpanExportResult

from mcp_agent.config import TracePathSettings
from mcp_agent.logging.logger import get_logger

logger = get_logger(__name__)


class FileSpanExporter(SpanExporter):
    """Implementation of :class:`SpanExporter` that writes spans as JSON to a file."""

    def __init__(
        self,
        service_name: str | None = None,
        session_id: str | None = None,
        formatter: Callable[[ReadableSpan], str] = lambda span: span.to_json(
            indent=None
        )
        + linesep,
        path_settings: TracePathSettings | None = None,
        custom_path: str | None = None,
    ):
        self.formatter = formatter
        self.service_name = service_name
        self.session_id = session_id or str(uuid.uuid4())
        self.path_settings = path_settings or TracePathSettings()
        self.custom_path = custom_path
        self.filepath = Path(self._get_trace_filename())
        # Create directory if it doesn't exist
        self.filepath.parent.mkdir(parents=True, exist_ok=True)

    def _get_trace_filename(self) -> str:
        """Generate a trace filename based on the path settings."""
        # If custom_path is provided, use it directly
        if self.custom_path:
            return self.custom_path

        path_pattern = self.path_settings.path_pattern
        unique_id_type = self.path_settings.unique_id

        if unique_id_type == "session_id":
            unique_id = self.session_id
        elif unique_id_type == "timestamp":
            now = datetime.now()
            time_format = self.path_settings.timestamp_format
            unique_id = now.strftime(time_format)
        else:
            raise ValueError(
                f"Invalid unique_id type: {unique_id_type}. Expected 'session_id' or 'timestamp'."
            )

        return path_pattern.replace("{unique_id}", unique_id)

    def export(self, spans: Sequence[ReadableSpan]) -> SpanExportResult:
        try:
            with open(self.filepath, "a", encoding="utf-8") as f:
                for span in spans:
                    f.write(self.formatter(span))
                    f.flush()  # Ensure writing to disk
            return SpanExportResult.SUCCESS
        except Exception as e:
            logger.error(f"Failed to export span to {self.filepath}: {e}")
            return SpanExportResult.FAILURE

    def force_flush(self, timeout_millis: int = 30000) -> bool:
        return True
