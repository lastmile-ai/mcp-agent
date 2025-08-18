"""
Utility functions for the Deep Orchestrator workflow.

This module provides common utilities like retry logic and helper functions.
"""

import asyncio
from typing import Any, Callable, Tuple, Type

from mcp_agent.logging.logger import get_logger

logger = get_logger(__name__)


async def retry_with_backoff(
    func: Callable,
    max_attempts: int = 3,
    initial_delay: float = 1.0,
    backoff_factor: float = 2.0,
    exceptions: Tuple[Type[Exception], ...] = (Exception,),
) -> Any:
    """
    Execute function with exponential backoff retry.

    Args:
        func: Async function to execute
        max_attempts: Maximum number of attempts
        initial_delay: Initial delay between retries in seconds
        backoff_factor: Multiplier for delay after each failure
        exceptions: Tuple of exception types to catch and retry

    Returns:
        Result from successful function execution

    Raises:
        Last exception if all attempts fail
    """
    last_exception = None
    delay = initial_delay

    for attempt in range(max_attempts):
        try:
            return await func()
        except exceptions as e:
            last_exception = e
            if attempt < max_attempts - 1:
                logger.warning(
                    f"Attempt {attempt + 1} failed: {e}. Retrying in {delay:.1f}s..."
                )
                await asyncio.sleep(delay)
                delay *= backoff_factor
            else:
                logger.error(f"All {max_attempts} attempts failed")

    raise last_exception
