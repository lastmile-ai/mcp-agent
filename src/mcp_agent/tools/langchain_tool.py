import inspect
from functools import wraps
from typing import Callable, Any, Optional, Union
from langchain_core.tools import BaseTool, StructuredTool


def from_langchain_tool(
    lc_tool: Union["BaseTool", object],
    *,
    name: Optional[str] = None,
    description: Optional[str] = None,
) -> Callable[..., Any]:
    """
    Convert a LangChain tool to a plain Python function.

    Args:
        lc_tool: The LangChain tool to convert (StructuredTool, BaseTool, or similar)
        name: Optional override for the function name
        description: Optional override for the function docstring

    Returns:
        Callable[..., Any]: Function with correct signature and metadata.
    """
    # Set name with fallback
    func_name = name or getattr(
        lc_tool, "name", getattr(lc_tool, "__name__", "tool_func")
    )

    # Set description with fallback
    func_doc = description or getattr(
        lc_tool, "description", getattr(lc_tool, "__doc__", "") or ""
    )

    # Handle different types of LangChain tools
    if isinstance(lc_tool, StructuredTool):
        # Keep each conversion's metadata independent of the original function.
        func = lc_tool.func
        if inspect.iscoroutinefunction(func):

            @wraps(func)
            async def wrapper(*args, **kwargs):
                return await func(*args, **kwargs)

        else:

            @wraps(func)
            def wrapper(*args, **kwargs):
                return func(*args, **kwargs)

        wrapper.__name__ = func_name
        wrapper.__doc__ = func_doc
        return wrapper

    elif hasattr(lc_tool, "_run"):
        # BaseTool with _run method - create wrapper preserving signature
        run_method = lc_tool._run

        # Create wrapper that preserves the signature of _run
        def wrapper(*args, **kwargs):
            return run_method(*args, **kwargs)

        # Copy signature from the _run method
        wrapper.__signature__ = inspect.signature(run_method)
        wrapper.__name__ = func_name
        wrapper.__doc__ = func_doc
        return wrapper

    elif hasattr(lc_tool, "run"):
        # Fallback to run method
        run_method = lc_tool.run

        def wrapper(*args, **kwargs):
            return run_method(*args, **kwargs)

        # Try to copy signature if available
        try:
            wrapper.__signature__ = inspect.signature(run_method)
        except (ValueError, TypeError):
            # If signature inspection fails, use generic signature
            pass

        wrapper.__name__ = func_name
        wrapper.__doc__ = func_doc
        return wrapper

    elif callable(lc_tool):
        # Tool is directly callable - create wrapper to avoid modifying original
        def wrapper(*args, **kwargs):
            return lc_tool(*args, **kwargs)

        # Copy signature and metadata if available
        try:
            wrapper.__signature__ = inspect.signature(lc_tool)
        except (ValueError, TypeError):
            pass

        wrapper.__name__ = func_name
        wrapper.__doc__ = func_doc
        return wrapper

    else:
        raise ValueError(
            "LangChain tool must have a 'func', 'run', or '_run' method, or be callable."
        )
