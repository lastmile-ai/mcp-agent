import inspect
from typing import Callable, Any, Optional

from autogen.tools import Tool as AG2Tool


def from_ag2_tool(
    ag2_tool: AG2Tool,
    *,
    name: Optional[str] = None,
    description: Optional[str] = None,
) -> Callable[..., Any]:
    """
    Convert an AG2 tool to a plain Python function.

    Args:
        ag2_tool: The AG2 Tool to convert.
        name: Optional override for the function name.
        description: Optional override for the function docstring.

    Returns:
        Callable[..., Any]: Function with correct signature and metadata.
    """
    # Set name with fallback
    if name:
        func_name = name
    elif hasattr(ag2_tool, "name") and ag2_tool.name:
        func_name = ag2_tool.name.replace(" ", "_").lower()
    else:
        func_name = "ag2_tool_func"

    # Set description with fallback
    if description:
        func_doc = description
    elif hasattr(ag2_tool, "description") and ag2_tool.description:
        func_doc = ag2_tool.description
    else:
        func_doc = ""

    # AG2 Tool exposes .func property with the underlying callable
    if hasattr(ag2_tool, "func") and ag2_tool.func is not None:
        func = ag2_tool.func
        func.__name__ = func_name
        func.__doc__ = func_doc
        return func

    elif callable(ag2_tool):
        # Tool is directly callable via __call__
        def wrapper(*args, **kwargs):
            return ag2_tool(*args, **kwargs)

        wrapper.__name__ = func_name
        wrapper.__doc__ = func_doc

        try:
            wrapper.__signature__ = inspect.signature(ag2_tool.func)
        except (ValueError, TypeError, AttributeError):
            pass

        return wrapper

    else:
        raise ValueError(
            "AG2 tool must have a 'func' property or be callable."
        )
