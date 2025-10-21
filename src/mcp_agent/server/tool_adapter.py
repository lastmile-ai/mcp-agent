"""
Utility functions for creating MCP tool adapters from functions.

This module provides shared logic for transforming function signatures
to be compatible with MCP tools, filtering out internal parameters like
app_ctx and adding required MCP Context parameters.
"""

import inspect
import typing as _typing
from typing import Any, Callable, Optional
from mcp.server.fastmcp import Context as _Ctx


def create_tool_adapter_signature(
    fn: Callable[..., Any],
    tool_name: str,
    description: Optional[str] = None,
) -> Callable[..., Any]:
    """
    Create a function with the transformed signature that app_server.py creates.

    This transforms the function signature by:
    1. Removing app_ctx parameter
    2. Adding ctx parameter with FastMCP Context type
    3. Preserving all other parameters and annotations

    Args:
        fn: The original function to adapt
        tool_name: Name of the tool
        description: Optional description for the tool

    Returns:
        A function with the transformed signature suitable for MCP tools

    This is used for validation in app.py to ensure the transformed
    signature can be converted to JSON schema.
    """
    sig = inspect.signature(fn)

    def _annotation_is_fast_ctx(annotation) -> bool:
        if _Ctx is None or annotation is inspect._empty:
            return False
        if annotation is _Ctx:
            return True
        try:
            origin = _typing.get_origin(annotation)
            if origin is not None:
                return any(
                    _annotation_is_fast_ctx(arg) for arg in _typing.get_args(annotation)
                )
        except Exception:
            pass
        try:
            return "fastmcp" in str(annotation)
        except Exception:
            return False

    existing_ctx_param = None
    for param in sig.parameters.values():
        if param.name == "app_ctx":
            continue
        annotation = param.annotation
        if annotation is inspect._empty and param.name in ("ctx", "context"):
            existing_ctx_param = param.name
            break
        if _annotation_is_fast_ctx(annotation):
            existing_ctx_param = param.name
            break
    return_ann = sig.return_annotation

    # Copy annotations and remove app_ctx
    ann = dict(getattr(fn, "__annotations__", {}))
    ann.pop("app_ctx", None)

    # Determine context parameter name
    ctx_param_name = existing_ctx_param or "ctx"
    if _Ctx is not None:
        ann[ctx_param_name] = _Ctx
    ann["return"] = getattr(fn, "__annotations__", {}).get("return", return_ann)

    # Filter parameters to remove app_ctx and, when needed, ctx/context placeholders
    params = []
    for p in sig.parameters.values():
        if p.name == "app_ctx":
            continue
        if existing_ctx_param is None and (
            (p.annotation is inspect._empty and p.name in ("ctx", "context"))
            or _annotation_is_fast_ctx(p.annotation)
        ):
            continue
        params.append(p)

    # Create ctx parameter when not already present
    if existing_ctx_param is None:
        ctx_param = inspect.Parameter(
            ctx_param_name,
            kind=inspect.Parameter.KEYWORD_ONLY,
            annotation=_Ctx,
        )
        signature_params = params + [ctx_param]
    else:
        signature_params = params

    # Create a dummy function with the transformed signature
    async def _transformed(**kwargs):
        pass

    # Set metadata on the transformed function
    _transformed.__annotations__ = ann
    _transformed.__name__ = tool_name
    _transformed.__doc__ = description or (fn.__doc__ or "")

    # Create new signature with filtered params + ctx param
    _transformed.__signature__ = inspect.Signature(
        parameters=signature_params, return_annotation=return_ann
    )

    return _transformed


def validate_tool_schema(fn: Callable[..., Any], tool_name: str) -> None:
    """
    Validate that a function can be converted to an MCP tool.

    This creates the adapter function with transformed signature and attempts
    to generate a JSON schema from it, raising a descriptive error if it fails.

    Args:
        fn: The function to validate
        tool_name: Name of the tool for error messages

    Raises:
        ValueError: If the function cannot be converted to a valid MCP tool
    """
    from mcp.server.fastmcp.tools import Tool as FastTool

    # Create the transformed function signature
    transformed_fn = create_tool_adapter_signature(fn, tool_name)

    try:
        # Try to create a FastTool to validate JSON schema generation
        FastTool.from_function(transformed_fn)
    except Exception as e:
        error_msg = str(e)
        if (
            "PydanticInvalidForJsonSchema" in error_msg
            or "Cannot generate a JsonSchema" in error_msg
        ):
            # Provide helpful context about problematic types
            sig = inspect.signature(fn)
            param_info = []
            for param_name, param in sig.parameters.items():
                # Skip parameters that will be filtered
                if param_name in ("app_ctx", "self", "cls"):
                    continue
                if param.annotation != inspect.Parameter.empty:
                    param_info.append(f"  - {param_name}: {param.annotation}")

            params_str = (
                "\n".join(param_info) if param_info else "  (no typed parameters)"
            )

            raise ValueError(
                f"Tool '{tool_name}' cannot be registered because its parameters or return type "
                f"cannot be serialized to JSON schema.\n"
                f"\nFunction parameters (after filtering):\n{params_str}\n"
                f"\nError: {error_msg}\n"
                f"\nCommon causes:\n"
                f"  - Parameters with types containing Callable fields (e.g., Agent, MCPApp)\n"
                f"  - Custom classes without proper Pydantic model definitions\n"
                f"  - Complex nested types that Pydantic cannot serialize\n"
                f"\nSuggestions:\n"
                f"  - Replace complex objects with simple identifiers (e.g., agent_name: str instead of agent: Agent)\n"
                f"  - Use primitive types (str, int, dict, list) for tool parameters\n"
                f"  - Create simplified Pydantic models for complex data structures\n"
                f"\nNote: The 'app_ctx' parameter is automatically filtered out and does not cause this error."
            ) from e
        # Re-raise other unexpected errors
        raise
