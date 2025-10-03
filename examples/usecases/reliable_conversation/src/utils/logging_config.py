"""
Custom logging configuration for RCM with readable formatting.
"""

import logging
import sys
from pathlib import Path
from .log_formatter import ReadableFormatter


def setup_readable_logging(
    level: str = "INFO",
    console_output: bool = True,
    file_output: bool = True,
    log_file: str = "logs/rcm.log",
    show_summaries: bool = True,
) -> None:
    """
    Set up readable logging for RCM with custom formatter.

    Args:
        level: Logging level (DEBUG, INFO, WARNING, ERROR)
        console_output: Whether to output to console
        file_output: Whether to output to file
        log_file: Path to log file
        show_summaries: Whether to show emoji summaries for key events
    """

    # Convert level string to logging constant
    numeric_level = getattr(logging, level.upper(), logging.INFO)

    # Create formatter
    formatter = ReadableFormatter(show_summaries=show_summaries)

    # Get root logger and clear existing handlers
    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.setLevel(numeric_level)

    # Console handler
    if console_output:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(numeric_level)
        console_handler.setFormatter(formatter)
        root_logger.addHandler(console_handler)

    # File handler
    if file_output:
        # Ensure log directory exists
        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)

        file_handler = logging.FileHandler(log_file)
        file_handler.setLevel(numeric_level)
        file_handler.setFormatter(formatter)
        root_logger.addHandler(file_handler)

    # Set specific logger levels to avoid excessive noise
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("openai").setLevel(logging.INFO)
    logging.getLogger("anthropic").setLevel(logging.INFO)


def setup_test_logging() -> None:
    """Set up logging specifically for test runs with minimal noise"""
    setup_readable_logging(
        level="DEBUG",
        console_output=True,
        file_output=True,
        log_file="logs/test_readable.log",
        show_summaries=True,
    )

    # Reduce noise from external libraries during tests
    logging.getLogger("httpx").setLevel(logging.ERROR)
    logging.getLogger("httpcore").setLevel(logging.ERROR)
    logging.getLogger("mcp").setLevel(logging.INFO)
