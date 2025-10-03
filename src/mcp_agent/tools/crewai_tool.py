import inspect
from typing import Callable, Any, Optional
from crewai.tools import BaseTool as CrewaiBaseTool
from pydantic import BaseModel
from pydantic_core import PydanticUndefined


def from_crewai_tool(
    crewai_tool: CrewaiBaseTool,
    *,
    name: Optional[str] = None,
    description: Optional[str] = None,
) -> Callable[..., Any]:
    """
    Convert a CrewAI tool to a plain Python function.

    Args:
        crewai_tool: The CrewAI tool to convert (BaseTool or similar)
        name: Optional override for the function name
        description: Optional override for the function docstring

    Returns:
        Callable[..., Any]: Function with correct signature and metadata.
    """
    if name:
        func_name = name
    elif hasattr(crewai_tool, "name") and crewai_tool.name:
        # CrewAI tool names may contain spaces - replace with underscores and lowercase
        func_name = crewai_tool.name.replace(" ", "_").lower()
    else:
        func_name = "crewai_tool_func"

    # Set description
    if description:
        func_doc = description
    elif hasattr(crewai_tool, "description") and crewai_tool.description:
        func_doc = crewai_tool.description
    else:
        func_doc = ""

    # Handle different types of CrewAI tools
    if hasattr(crewai_tool, "func"):
        # @tool decorated functions
        func = crewai_tool.func
        func.__name__ = func_name
        func.__doc__ = func_doc
        return func

    elif hasattr(crewai_tool, "args_schema") and hasattr(crewai_tool, "_run"):
        # Class-based tools with schema
        return _create_function_from_schema(
            crewai_tool._run, crewai_tool.args_schema, func_name, func_doc
        )

    elif hasattr(crewai_tool, "run"):
        # Fallback to run method with generic signature
        def wrapper(*args, **kwargs):
            return crewai_tool.run(*args, **kwargs)

        wrapper.__name__ = func_name
        wrapper.__doc__ = func_doc
        return wrapper

    elif callable(crewai_tool):
        # Tool is directly callable - create wrapper to avoid modifying original
        def wrapper(*args, **kwargs):
            return crewai_tool(*args, **kwargs)

        wrapper.__name__ = func_name
        wrapper.__doc__ = func_doc

        # Try to copy signature if available
        try:
            wrapper.__signature__ = inspect.signature(crewai_tool)
        except (ValueError, TypeError):
            pass

        return wrapper

    else:
        raise ValueError(
            "CrewAI tool must have a 'func', '_run', 'run' method, or be callable."
        )


def _create_function_from_schema(
    run_method: Callable, schema: type[BaseModel], func_name: str, func_doc: str
) -> Callable:
    """Create a function with proper signature from a Pydantic schema."""
    if not hasattr(schema, "model_fields") or not schema.model_fields:
        # No parameters - create a function that takes no args
        def schema_func():
            return run_method()

        schema_func.__name__ = func_name
        schema_func.__doc__ = func_doc
        return schema_func

    # Get field information from the schema
    fields = schema.model_fields

    # Create parameter specifications
    required_params = []
    optional_params = []
    annotations = {}

    for field_name, field_info in fields.items():
        # Extract type annotation
        annotations[field_name] = field_info.annotation

        # Handle defaults - check for both ... (Ellipsis) and PydanticUndefined
        if (
            field_info.default is not ...
            and field_info.default is not PydanticUndefined
        ):
            # Optional parameter (has default)
            optional_params.append(
                inspect.Parameter(
                    field_name,
                    inspect.Parameter.POSITIONAL_OR_KEYWORD,
                    default=field_info.default,
                    annotation=field_info.annotation,
                )
            )
        else:
            # Required parameter (no default)
            required_params.append(
                inspect.Parameter(
                    field_name,
                    inspect.Parameter.POSITIONAL_OR_KEYWORD,
                    annotation=field_info.annotation,
                )
            )

    # Combine parameters: required first, then optional
    params = required_params + optional_params

    # Create new signature
    sig = inspect.Signature(params)

    # Create function dynamically
    def schema_func(*args, **kwargs):
        # Bind arguments to match the schema
        bound = sig.bind(*args, **kwargs)
        bound.apply_defaults()
        return run_method(**bound.arguments)

    # Set metadata
    schema_func.__name__ = func_name
    schema_func.__doc__ = func_doc
    schema_func.__signature__ = sig
    schema_func.__annotations__ = annotations

    return schema_func
