"""Retry utilities for CLI operations."""

import asyncio
import time
from typing import Any, Callable, Optional

from mcp_agent.cli.core.api_client import UnauthenticatedError
from mcp_agent.cli.exceptions import CLIError
from mcp_agent.cli.utils.ux import print_warning


class RetryError(Exception):
    """Exception raised when all retry attempts are exhausted."""

    def __init__(self, original_error: Exception, attempts: int):
        self.original_error = original_error
        self.attempts = attempts
        super().__init__(
            f"Failed after {attempts} attempts. Last error: {original_error}"
        )


def is_retryable_error(error: Exception) -> bool:
    """Determine if an error should trigger a retry.

    Args:
        error: The exception to evaluate

    Returns:
        True if the error is retryable, False otherwise
    """
    if isinstance(error, UnauthenticatedError):
        return False

    if isinstance(error, CLIError):
        return error.retriable

    return True


def retry_with_exponential_backoff(
    func: Callable,
    max_attempts: int = 3,
    initial_delay: float = 1.0,
    backoff_multiplier: float = 2.0,
    max_delay: float = 60.0,
    retryable_check: Optional[Callable[[Exception], bool]] = None,
    *args,
    **kwargs,
) -> Any:
    """Retry a function with exponential backoff.

    Args:
        func: The function to retry
        max_attempts: Maximum number of attempts (including the first one)
        initial_delay: Initial delay in seconds before first retry
        backoff_multiplier: Multiplier for delay between attempts
        max_delay: Maximum delay between attempts
        retryable_check: Function to determine if an error is retryable
        *args: Arguments to pass to func
        **kwargs: Keyword arguments to pass to func

    Returns:
        Result of the successful function call

    Raises:
        RetryError: If all attempts fail with a retryable error
        Exception: The original exception if it's not retryable
    """
    if retryable_check is None:
        retryable_check = is_retryable_error

    last_exception = None
    delay = initial_delay

    for attempt in range(1, max_attempts + 1):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            last_exception = e

            if attempt == max_attempts or not retryable_check(e):
                break

            print_warning(
                f"Attempt {attempt}/{max_attempts} failed: {e}. Retrying in {delay:.1f}s..."
            )

            time.sleep(delay)
            delay = min(delay * backoff_multiplier, max_delay)

    if last_exception:
        if max_attempts > 1 and retryable_check(last_exception):
            raise RetryError(last_exception, max_attempts) from last_exception
        else:
            raise last_exception

    raise RuntimeError("Unexpected error in retry logic")


async def retry_async_with_exponential_backoff(
    func: Callable,
    max_attempts: int = 3,
    initial_delay: float = 1.0,
    backoff_multiplier: float = 2.0,
    max_delay: float = 60.0,
    retryable_check: Optional[Callable[[Exception], bool]] = None,
    *args,
    **kwargs,
) -> Any:
    """Async version of retry with exponential backoff.

    Args:
        func: Async function to retry
        max_attempts: Maximum number of attempts (including the first one)
        initial_delay: Initial delay in seconds before first retry
        backoff_multiplier: Multiplier for delay between attempts
        max_delay: Maximum delay between attempts
        retryable_check: Function to determine if an error is retryable
        *args: Arguments to pass to func
        **kwargs: Keyword arguments to pass to func

    Returns:
        Result of the successful function call

    Raises:
        RetryError: If all attempts fail with a retryable error
        Exception: The original exception if it's not retryable
    """
    if retryable_check is None:
        retryable_check = is_retryable_error

    last_exception = None
    delay = initial_delay

    for attempt in range(1, max_attempts + 1):
        try:
            return await func(*args, **kwargs)
        except Exception as e:
            last_exception = e

            if isinstance(e, asyncio.CancelledError):
                raise

            if attempt == max_attempts or not retryable_check(e):
                break

            print_warning(
                f"Attempt {attempt}/{max_attempts} failed: {e}. Retrying in {delay:.1f}s..."
            )

            await asyncio.sleep(delay)
            delay = min(delay * backoff_multiplier, max_delay)

    if last_exception:
        if max_attempts > 1 and retryable_check(last_exception):
            raise RetryError(last_exception, max_attempts) from last_exception
        else:
            raise last_exception

    raise RuntimeError("Unexpected error in retry logic")
